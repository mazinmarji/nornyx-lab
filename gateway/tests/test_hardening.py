"""Abuse controls and log safety, attacked directly rather than assumed.

Two gaps this file exists to close, both found by asking "what does the
behavioural suite not reach?":

* the body-size cap has a second branch — a request with no ``Content-Length`` —
  that the test client never exercises, because it always sets the header;
* the safe-logging claim is about what is *absent*, and absence is only proved
  by capturing the log stream while something confidential is in flight.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from conftest import SESSION_MARKER, make_payload
from fastapi.testclient import TestClient

from nornyx_feedback_gateway.app import BodySizeLimitMiddleware, RateLimiter, create_app
from nornyx_feedback_gateway.config import GatewayConfig, load_config

TOKEN = "ghp-test-token-value-never-echoed"


# --------------------------------------------------------------- body limits
def test_a_chunked_request_is_cut_off_without_a_content_length_header() -> None:
    """The branch the HTTP client cannot reach, driven at the ASGI layer.

    A caller that omits ``Content-Length`` must not be able to stream past the
    cap. The middleware counts bytes as they arrive and stops the request.
    """

    received: list[int] = []

    async def app(scope, receive, send):
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            total += len(message.get("body", b""))
            if not message.get("more_body"):
                break
        received.append(total)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    limited = BodySizeLimitMiddleware(app, max_bytes=100)
    chunks = [
        {"type": "http.request", "body": b"x" * 60, "more_body": True},
        {"type": "http.request", "body": b"x" * 60, "more_body": True},
        {"type": "http.request", "body": b"x" * 60, "more_body": False},
    ]
    queue = list(chunks)

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message):
        return None

    asyncio.run(limited({"type": "http", "headers": []}, receive, send))

    assert received == [60], "the stream was allowed to continue past the cap"


def test_a_non_http_scope_passes_through_untouched() -> None:
    seen: list[str] = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(
        BodySizeLimitMiddleware(app, max_bytes=10)(
            {"type": "lifespan"}, lambda: None, lambda message: None
        )
    )
    assert seen == ["lifespan"]


def test_a_malformed_content_length_is_not_trusted_as_a_bypass(config, sink) -> None:
    """A garbage header must fall back to counting, not to unlimited."""

    small = GatewayConfig(
        github_repository="owner/name",
        github_token=TOKEN,
        database_path=config.database_path,
        max_body_bytes=200,
    )
    with TestClient(create_app(config=small, sink=sink)) as api:
        response = api.post(
            "/v1/feedback",
            content=b"x" * 5000,
            headers={"content-type": "application/json", "content-length": "not-a-number"},
        )

    assert response.status_code in (400, 413, 422)
    assert sink.calls == []


# --------------------------------------------------------------- rate limiter
def test_the_rate_limiter_window_rolls_forward() -> None:
    now = [0.0]
    limiter = RateLimiter(per_minute=2, clock=lambda: now[0])

    assert limiter.allow("a") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False

    now[0] = 61.0
    assert limiter.allow("a") is True, "the window never expired"


def test_one_client_cannot_exhaust_another_clients_budget() -> None:
    limiter = RateLimiter(per_minute=1, clock=lambda: 0.0)

    assert limiter.allow("first") is True
    assert limiter.allow("first") is False
    assert limiter.allow("second") is True, "buckets are not per client"


def test_a_zero_limit_disables_rate_limiting_rather_than_blocking_everything() -> None:
    """A misconfiguration must not become a denial of the legitimate path."""

    limiter = RateLimiter(per_minute=0, clock=lambda: 0.0)
    assert all(limiter.allow("anyone") for _ in range(100))


# ----------------------------------------------------------------- safe logs
def test_no_learner_text_or_credential_reaches_the_log_stream(config, sink, caplog) -> None:
    secret_comment = "MY-PRIVATE-COMMENT-TEXT plus my email me@example.test"
    payload = make_payload(comment=secret_comment)

    with caplog.at_level(logging.DEBUG, logger="nornyx.feedback.gateway"):
        with TestClient(create_app(config=config, sink=sink)) as api:
            api.post("/v1/feedback", json=payload)

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "MY-PRIVATE-COMMENT-TEXT" not in logged
    assert "me@example.test" not in logged
    assert TOKEN not in logged
    assert "nornyx-lab-feedback-intake" not in logged
    assert "testclient" not in logged, "the client address reached the log"
    # What it *should* say: a truncated *marker* and an outcome. Not the UUID —
    # a write key has no business in a log file either.
    assert SESSION_MARKER[:8] in logged
    assert "created" in logged
    assert "7f21ac1e" not in logged


def test_a_failure_logs_the_classified_code_and_nothing_more(config, sink, caplog) -> None:
    from nornyx_feedback_gateway.github import GitHubError

    sink.fail_on["create_issue"] = GitHubError(
        "forbidden", f"upstream said {TOKEN} on repo {config.github_repository}", status=403
    )
    with caplog.at_level(logging.DEBUG, logger="nornyx.feedback.gateway"):
        with TestClient(create_app(config=config, sink=sink)) as api:
            api.post("/v1/feedback", json=make_payload())

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "forbidden" in logged
    assert TOKEN not in logged
    assert "nornyx-lab-feedback-intake" not in logged


# ------------------------------------------------------------- configuration
def test_the_configuration_object_never_prints_its_credential() -> None:
    config = GatewayConfig(github_repository="owner/name", github_token=TOKEN)
    assert TOKEN not in repr(config)
    assert "owner/name" in repr(config)


def test_configuration_is_read_from_an_injected_mapping_not_only_the_process() -> None:
    config = load_config(
        {
            "NORNYX_FEEDBACK_GITHUB_REPOSITORY": "owner/intake",
            "NORNYX_FEEDBACK_GITHUB_TOKEN": TOKEN,
            "NORNYX_FEEDBACK_DESTINATION_VISIBILITY": "public",
            "NORNYX_FEEDBACK_ISSUE_LABELS": "learner-feedback, research",
            "NORNYX_FEEDBACK_RATE_LIMIT_PER_MINUTE": "5",
        }
    )
    assert config.github_configured is True
    assert config.destination_visibility == "public"
    assert config.issue_labels == ("learner-feedback", "research")
    assert config.rate_limit_per_minute == 5


def test_an_unconfigured_environment_yields_a_usable_local_default() -> None:
    """Positive control: no configuration is a valid state, not a crash."""

    config = load_config({})
    assert config.github_configured is False
    assert config.destination_visibility == "unknown"
    assert config.issue_labels == ("learner-feedback",)


@pytest.mark.parametrize(
    "environ",
    [
        {"NORNYX_FEEDBACK_GITHUB_REPOSITORY": "not-a-repo"},
        {"NORNYX_FEEDBACK_GITHUB_REPOSITORY": "owner/name/extra"},
        {"NORNYX_FEEDBACK_GITHUB_REPOSITORY": "../../../etc"},
        {"NORNYX_FEEDBACK_DESTINATION_VISIBILITY": "sort-of-private"},
        {"NORNYX_FEEDBACK_RATE_LIMIT_PER_MINUTE": "lots"},
        {"NORNYX_FEEDBACK_ISSUE_LABELS": "has`backtick"},
    ],
)
def test_an_unusable_configuration_fails_at_startup_not_at_request_time(environ) -> None:
    from nornyx_feedback_gateway.config import ConfigurationError

    with pytest.raises(ConfigurationError):
        load_config(environ)
