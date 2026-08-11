"""The hosted intake service.

Scope, stated as a boundary rather than as a wish: this service receives a
versioned feedback payload, validates it, renders it, and writes one GitHub
issue. It does not execute learner content, evaluate templates, run commands,
modify files, generate code, open pull requests, invoke agents, or merge
anything. Feedback is data.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .concurrency import KeyedLocks, RateLimiter
from .config import SCHEMA_ID, GatewayConfig, load_config
from .digest import DigestMismatch, verified_digest
from .github import GitHubError, GitHubSink, UrllibGitHubSink
from .models import AcceptedResponse, ErrorResponse, FeedbackPayload, HealthResponse
from .store import SyncStore
from .sync import synchronise

LOGGER = logging.getLogger("nornyx.feedback.gateway")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class BodySizeLimitMiddleware:
    """Reject oversized requests before anything buffers them.

    Pure ASGI rather than a ``BaseHTTPMiddleware`` subclass on purpose: the
    limit has to apply to the *stream*, not to a body that has already been read
    into memory. A declared ``Content-Length`` is rejected outright; a chunked
    request is counted as it arrives and cut off the moment it exceeds the cap.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = None
        for key, value in scope.get("headers", ()):
            if key == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = None
                break
        if declared is not None and declared > self.max_bytes:
            await _send_error(send, 413, "payload_too_large", "The feedback payload is too large.")
            return

        received = 0
        exceeded = False

        async def counting_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
                    return {"type": "http.disconnect"}
            return message

        await self.app(scope, counting_receive, send)
        if exceeded:  # pragma: no cover - the disconnect already ended the response
            LOGGER.warning("request body exceeded the configured limit")


async def _send_error(send: Send, status: int, code: str, message: str) -> None:
    body = ErrorResponse(code=code, message=message).model_dump_json().encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def create_app(
    *,
    config: GatewayConfig | None = None,
    sink: GitHubSink | None = None,
    store: SyncStore | None = None,
    clock: Callable[[], str] = _utc_now,
) -> FastAPI:
    """Build the intake service.

    ``sink`` is injectable so every test in CI runs against a substituted GitHub
    boundary. No test in this repository requires a real credential.
    """

    settings = config or load_config()
    app = FastAPI(
        title="Nornyx Feedback Gateway",
        version="0.1.0",
        description=(
            "Receives consented Nornyx Academy learner feedback and records one GitHub issue "
            "per feedback session. Holds the only GitHub write credential in the architecture."
        ),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.config = settings
    app.state.store = store or SyncStore(settings.database_path)
    app.state.sink = sink
    app.state.limiter = RateLimiter(per_minute=settings.rate_limit_per_minute)
    # Synchronisation for one session must not interleave with itself. Held
    # across lookup, recovery, create/update, and remember — the whole sequence
    # that decides whether an issue already exists.
    app.state.session_locks = KeyedLocks()
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)

    def resolve_sink() -> GitHubSink:
        if app.state.sink is not None:
            return app.state.sink
        return UrllibGitHubSink(settings)

    @app.middleware("http")
    async def hardening(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            github_configured=settings.github_configured,
            destination_visibility=settings.destination_visibility,
        )

    @app.post("/v1/feedback", response_model=AcceptedResponse, status_code=202)
    def receive(payload: FeedbackPayload, request: Request) -> Any:
        client = request.client.host if request.client else "unknown"
        if not app.state.limiter.allow(client):
            return _json_error(429, "rate_limited", "Too many requests. Try again shortly.")

        session_id = payload.session.session_id

        # The submitted digest is a field in an unauthenticated request. Derive
        # the real one and refuse a mismatch before anything is written
        # anywhere, so a forged or stale digest can neither suppress an update
        # nor claim another session's identity.
        try:
            digest = verified_digest(payload)
        except DigestMismatch:
            LOGGER.warning("rejected session %s: payload digest mismatch", session_id[:8])
            return _json_error(
                422,
                "digest_mismatch",
                "The payload does not match the digest submitted with it.",
            )

        if not settings.github_configured:
            LOGGER.warning("feedback rejected: this deployment has no GitHub destination")
            return _json_error(
                503,
                "github_not_configured",
                "This intake is not configured with a delivery destination.",
            )

        try:
            with app.state.session_locks.hold(session_id):
                result = synchronise(
                    payload,
                    sink=resolve_sink(),
                    store=app.state.store,
                    now=clock(),
                    digest=digest,
                )
        except GitHubError as exc:
            # Only the classified code is reported. A GitHub error body can name
            # the intake repository, and a learner installation must not receive
            # deployment detail, a stack trace, or a raw upstream response.
            LOGGER.warning("github boundary failed for session %s: %s", session_id[:8], exc.code)
            status = 503 if exc.retryable else 502
            return _json_error(status, exc.code, "The feedback destination did not accept it.")

        # Safe log: a truncated session id and an outcome. No text, no context,
        # no client address, no credential.
        LOGGER.info("session %s %s issue %d", session_id[:8], result.status, result.issue_number)
        return AcceptedResponse(
            status=result.status,
            issue_number=result.issue_number,
            destination_visibility=settings.destination_visibility,
        )

    return app


def _json_error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(code=code, message=message).model_dump(),
        headers={"Cache-Control": "no-store"},
    )


__all__ = ["SCHEMA_ID", "BodySizeLimitMiddleware", "create_app"]
