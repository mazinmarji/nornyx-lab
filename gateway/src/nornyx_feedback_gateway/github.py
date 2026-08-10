"""The GitHub boundary: the only place in the architecture with write authority.

Two things live here and nothing else does: a narrow ``GitHubSink`` protocol the
rest of the service talks to, and one standard-library implementation of it.
Keeping the surface this small is what lets every test in CI substitute a fake
sink and still exercise the real decision logic — no test in this repository
requires a GitHub credential, and none may.

Outbound requests use ``urllib.request`` deliberately. The gateway is the piece
of this system that handles untrusted internet input and holds a credential, so
its dependency surface is kept to the framework and its validator; adding an
HTTP client library here would widen the supply chain around the token for no
behavioural gain. Every call carries an explicit timeout.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol

from .config import GatewayConfig

USER_AGENT = "nornyx-feedback-gateway/0.1"
API_VERSION = "2022-11-28"


class GitHubError(RuntimeError):
    """A failure at the GitHub boundary, classified into a stable code.

    The code — never the underlying response text — is what the rest of the
    service is allowed to act on and report. A GitHub error body can contain
    the repository name or other deployment detail, and a learner installation
    has no business receiving it.
    """

    def __init__(self, code: str, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status

    @property
    def retryable(self) -> bool:
        """Whether trying the same call again could plausibly succeed."""

        return self.code in {"timeout", "unreachable", "server_error"}


def classify_status(status: int) -> str:
    if status == 401:
        return "unauthorized"
    if status == 403:
        return "forbidden"
    if status == 404:
        return "not_found"
    if status == 422:
        return "rejected"
    if 500 <= status < 600:
        return "server_error"
    return "unexpected_status"


class GitHubSink(Protocol):
    """What the synchronisation logic needs from GitHub, and nothing more.

    Note what is absent: no delete, no close, no label mutation, no pull
    request, no workflow dispatch, no repository write of any other kind.
    """

    def find_issue(self, *, title: str, marker: str) -> int | None: ...

    def create_issue(self, *, title: str, body: str) -> int: ...

    def update_issue(self, *, number: int, body: str) -> None: ...


class UrllibGitHubSink:
    """Real GitHub implementation over the standard library."""

    def __init__(self, config: GatewayConfig, *, opener: Any | None = None) -> None:
        if not config.github_configured:
            # Fail closed rather than attempting an unauthenticated write.
            raise GitHubError("github_not_configured", "no GitHub repository and token configured")
        self._config = config
        self._opener = opener or urllib.request.build_opener()

    # ------------------------------------------------------------------ plumbing
    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self._config.github_api.rstrip('/')}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url=url, data=data, method=method)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", API_VERSION)
        request.add_header("User-Agent", USER_AGENT)
        request.add_header("Authorization", f"Bearer {self._config.github_token}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with self._opener.open(
                request, timeout=self._config.github_timeout_seconds
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:  # noqa: B904 - re-raised as a classified error
            raise GitHubError(
                classify_status(exc.code),
                f"GitHub returned {exc.code}",
                status=exc.code,
            ) from exc
        except TimeoutError as exc:
            raise GitHubError(
                "timeout", "GitHub did not respond within the configured timeout"
            ) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                raise GitHubError("timeout", "GitHub did not respond in time") from exc
            raise GitHubError("unreachable", "GitHub could not be reached") from exc
        except OSError as exc:
            raise GitHubError("unreachable", "GitHub could not be reached") from exc
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubError(
                "malformed_response", "GitHub returned an unreadable response"
            ) from exc

    # -------------------------------------------------------------------- sink
    def find_issue(self, *, title: str, marker: str) -> int | None:
        """Recover the issue for a session without relying on local state.

        Uses the issues listing rather than the search API: listing is
        immediately consistent, whereas search indexing lags, and a lagging
        index is exactly how a retry after an ambiguous timeout would create a
        duplicate. The deterministic title narrows the candidates; the full
        session marker in the body is what actually confirms identity.
        """

        labels = urllib.parse.quote(",".join(self._config.issue_labels))
        repository = self._config.github_repository
        for page in range(1, self._config.recovery_page_limit + 1):
            path = f"/repos/{repository}/issues?state=all&labels={labels}&per_page=100&page={page}"
            batch = self._request("GET", path)
            if not isinstance(batch, list):
                raise GitHubError("malformed_response", "GitHub returned an unexpected issue list")
            if not batch:
                return None
            for item in batch:
                if not isinstance(item, dict) or item.get("title") != title:
                    continue
                body = item.get("body")
                number = item.get("number")
                if isinstance(body, str) and marker in body and isinstance(number, int):
                    return number
            if len(batch) < 100:
                return None
        return None

    def create_issue(self, *, title: str, body: str) -> int:
        created = self._request(
            "POST",
            f"/repos/{self._config.github_repository}/issues",
            {"title": title, "body": body, "labels": list(self._config.issue_labels)},
        )
        if not isinstance(created, dict) or not isinstance(created.get("number"), int):
            # The issue may well exist. Saying so is what lets the caller retry
            # into recovery instead of creating a second one.
            raise GitHubError(
                "malformed_response",
                "GitHub accepted the issue but did not return a usable number",
            )
        return int(created["number"])

    def update_issue(self, *, number: int, body: str) -> None:
        self._request(
            "PATCH",
            f"/repos/{self._config.github_repository}/issues/{number}",
            {"body": body},
        )


__all__ = ["API_VERSION", "GitHubError", "GitHubSink", "UrllibGitHubSink", "classify_status"]
