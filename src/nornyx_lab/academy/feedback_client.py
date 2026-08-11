"""The only outbound network path in the academy's feedback feature.

The academy never talks to GitHub. It talks to one configured gateway, and only
after the learner has explicitly consented. Keeping that surface to a single
small module is what makes "no learner installation holds GitHub authority" a
statement about code rather than about intent — there is nowhere else a token
could be used, because there is no other outbound call.

Three deliberate properties:

* **Standard library only.** No new dependency is introduced for this, so the
  learner installation's supply chain is unchanged by the feature.
* **Explicit timeout, no redirects.** A redirect is a request to send the
  learner's words somewhere other than the configured endpoint, so redirects are
  refused rather than followed.
* **Transport, not policy.** This module never decides whether to send. It is
  handed a payload that consent has already authorised.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

USER_AGENT = "nornyx-academy-feedback/1.0"
DEFAULT_TIMEOUT_SECONDS = 10.0

#: Hosts for which plain HTTP is accepted, so an operator can exercise a gateway
#: on their own machine. Everything else must be HTTPS: learner free text is not
#: going over the open internet in the clear because a configuration file said so.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


@dataclass(frozen=True)
class TransportResult:
    """The outcome of one delivery attempt, classified.

    ``error_code`` is a coarse label. Raw response bodies, URLs, headers, and
    tracebacks stop here: nothing downstream stores or displays them.
    """

    ok: bool
    outcome: str | None = None
    issue_number: int | None = None
    error_code: str | None = None


class FeedbackTransport(Protocol):
    def send(self, endpoint: str, payload: dict[str, Any]) -> TransportResult: ...


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def endpoint_is_acceptable(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    if parsed.scheme == "https":
        return True
    return parsed.scheme == "http" and (parsed.hostname or "") in LOOPBACK_HOSTS


class UrllibFeedbackTransport:
    """Posts one payload to the configured gateway and classifies the answer."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        opener: Any | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._opener = opener or urllib.request.build_opener(NoRedirect)

    def send(self, endpoint: str, payload: dict[str, Any]) -> TransportResult:
        if not endpoint_is_acceptable(endpoint):
            return TransportResult(ok=False, error_code="insecure_endpoint")
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url=endpoint, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        request.add_header("User-Agent", USER_AGENT)
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            if status in (301, 302, 303, 307, 308):
                return TransportResult(ok=False, error_code="redirect_refused")
            if status == 429:
                return TransportResult(ok=False, error_code="rate_limited")
            if 400 <= status < 500:
                return TransportResult(ok=False, error_code="rejected")
            return TransportResult(ok=False, error_code="gateway_error")
        except TimeoutError:
            return TransportResult(ok=False, error_code="timeout")
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                return TransportResult(ok=False, error_code="timeout")
            return TransportResult(ok=False, error_code="unreachable")
        except OSError:
            return TransportResult(ok=False, error_code="unreachable")

        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return TransportResult(ok=False, error_code="malformed_response")
        if not isinstance(document, dict):
            return TransportResult(ok=False, error_code="malformed_response")
        outcome = document.get("status")
        number = document.get("issue_number")
        if outcome not in {"created", "updated", "unchanged"} or not isinstance(number, int):
            # A 2xx with an unrecognised body is not a delivery confirmation.
            # Recording it as success is how a sync state starts lying.
            return TransportResult(ok=False, error_code="malformed_response")
        return TransportResult(ok=True, outcome=outcome, issue_number=number)


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "LOOPBACK_HOSTS",
    "FeedbackTransport",
    "TransportResult",
    "UrllibFeedbackTransport",
    "endpoint_is_acceptable",
]
