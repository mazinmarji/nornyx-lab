"""The real ``urllib`` GitHub client, driven by a substituted opener.

This covers the implementation that would talk to github.com in production
without ever contacting it: the opener is replaced, so what is under test is the
request construction, the status classification, and the recovery paging — the
parts that decide whether a retry duplicates an issue or not.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from nornyx_feedback_gateway.config import GatewayConfig
from nornyx_feedback_gateway.github import GitHubError, UrllibGitHubSink, classify_status

TOKEN = "ghp-secret-value"


class FakeResponse(io.BytesIO):
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class RecordingOpener:
    """Captures the outbound request and replays a scripted response."""

    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[str, str, dict[str, str], object]] = []
        self.timeouts: list[float | None] = []

    def open(self, request, timeout=None):  # noqa: ANN001 - mirrors urllib's signature
        payload = json.loads(request.data.decode("utf-8")) if request.data else None
        self.requests.append((request.method, request.full_url, dict(request.headers), payload))
        self.timeouts.append(timeout)
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return FakeResponse(json.dumps(nxt).encode("utf-8"))


def _config(**overrides) -> GatewayConfig:
    base = {
        "github_repository": "owner/intake",
        "github_token": TOKEN,
        "github_api": "https://api.github.test",
        "github_timeout_seconds": 7.5,
        "database_path": ":memory:",
    }
    base.update(overrides)
    return GatewayConfig(**base)


def test_an_unconfigured_sink_refuses_to_be_constructed() -> None:
    with pytest.raises(GitHubError) as caught:
        UrllibGitHubSink(GatewayConfig())
    assert caught.value.code == "github_not_configured"


def test_create_sends_an_authorised_bounded_request() -> None:
    opener = RecordingOpener([{"number": 42}])
    sink = UrllibGitHubSink(_config(issue_labels=("learner-feedback", "intake")), opener=opener)

    assert sink.create_issue(title="[Learner Feedback] Session abcd1234", body="body") == 42

    method, url, headers, payload = opener.requests[0]
    assert method == "POST"
    assert url == "https://api.github.test/repos/owner/intake/issues"
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["X-github-api-version"] == "2022-11-28"
    assert payload == {
        "title": "[Learner Feedback] Session abcd1234",
        "body": "body",
        # Labels come from configuration. There is no code path by which a
        # learner-supplied value could reach this list.
        "labels": ["learner-feedback", "intake"],
    }
    # An outbound call with no timeout is how a hosted service hangs forever.
    assert opener.timeouts == [7.5]


def test_update_targets_the_named_issue_and_changes_only_the_body() -> None:
    opener = RecordingOpener([{"number": 42}])
    sink = UrllibGitHubSink(_config(), opener=opener)

    sink.update_issue(number=42, body="new body")

    method, url, _, payload = opener.requests[0]
    assert method == "PATCH"
    assert url == "https://api.github.test/repos/owner/intake/issues/42"
    # Notably absent: state, labels, title, assignees. This sink cannot close an
    # issue or relabel one even if something asked it to.
    assert payload == {"body": "new body"}


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "unauthorized"),
        (403, "forbidden"),
        (404, "not_found"),
        (422, "rejected"),
        (500, "server_error"),
        (503, "server_error"),
        (418, "unexpected_status"),
    ],
)
def test_http_statuses_map_to_stable_codes(status, code) -> None:
    assert classify_status(status) == code
    opener = RecordingOpener(
        [urllib.error.HTTPError("https://api.github.test", status, "boom", {}, None)]
    )
    sink = UrllibGitHubSink(_config(), opener=opener)

    with pytest.raises(GitHubError) as caught:
        sink.create_issue(title="t", body="b")

    assert caught.value.code == code
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize(
    ("raised", "code"),
    [
        (TimeoutError("slow"), "timeout"),
        (urllib.error.URLError(TimeoutError("slow")), "timeout"),
        (urllib.error.URLError("no route to host"), "unreachable"),
        (OSError("connection reset"), "unreachable"),
    ],
)
def test_transport_failures_map_to_retryable_codes(raised, code) -> None:
    opener = RecordingOpener([raised])
    sink = UrllibGitHubSink(_config(), opener=opener)

    with pytest.raises(GitHubError) as caught:
        sink.create_issue(title="t", body="b")

    assert caught.value.code == code
    assert caught.value.retryable is True


def test_a_create_that_returns_no_usable_number_is_reported_as_ambiguous() -> None:
    """GitHub may have created the issue. Claiming success would be a lie."""

    opener = RecordingOpener([{"unexpected": "shape"}])
    sink = UrllibGitHubSink(_config(), opener=opener)

    with pytest.raises(GitHubError) as caught:
        sink.create_issue(title="t", body="b")

    assert caught.value.code == "malformed_response"


def test_unreadable_response_bodies_are_classified_not_crashed() -> None:
    class BrokenOpener:
        def open(self, request, timeout=None):  # noqa: ANN001
            return FakeResponse(b"<html>not json</html>")

    sink = UrllibGitHubSink(_config(), opener=BrokenOpener())
    with pytest.raises(GitHubError) as caught:
        sink.create_issue(title="t", body="b")
    assert caught.value.code == "malformed_response"


def test_recovery_matches_on_the_title_and_confirms_with_the_full_marker() -> None:
    marker = "<!-- nornyx-feedback-session: 7f21ac1e-4b3d-4c2a-9f10-2b5d6e7a8c90 -->"
    opener = RecordingOpener(
        [
            [
                {"number": 5, "title": "[Learner Feedback] Session 7f21ac1e", "body": "different"},
                {"number": 6, "title": "unrelated issue", "body": marker},
                {"number": 7, "title": "[Learner Feedback] Session 7f21ac1e", "body": marker},
            ]
        ]
    )
    sink = UrllibGitHubSink(_config(), opener=opener)

    # A title collision alone is not identity, and a marker alone is not either.
    # Only the pair confirms the session.
    assert sink.find_issue(title="[Learner Feedback] Session 7f21ac1e", marker=marker) == 7
    method, url, _, _ = opener.requests[0]
    assert method == "GET"
    assert "state=all" in url and "labels=learner-feedback" in url and "page=1" in url


def test_recovery_pages_until_the_list_runs_out() -> None:
    marker = "<!-- nornyx-feedback-session: abc -->"
    full_page = [{"number": n, "title": "other", "body": ""} for n in range(100)]
    opener = RecordingOpener([full_page, [{"number": 999, "title": "wanted", "body": marker}]])
    sink = UrllibGitHubSink(_config(), opener=opener)

    assert sink.find_issue(title="wanted", marker=marker) == 999
    assert len(opener.requests) == 2


def test_recovery_stops_at_the_configured_page_limit() -> None:
    full_page = [{"number": n, "title": "other", "body": ""} for n in range(100)]
    opener = RecordingOpener([full_page] * 3)
    sink = UrllibGitHubSink(_config(recovery_page_limit=3), opener=opener)

    assert sink.find_issue(title="wanted", marker="m") is None
    assert len(opener.requests) == 3


def test_recovery_rejects_an_unexpected_list_shape() -> None:
    opener = RecordingOpener([{"message": "Not Found"}])
    sink = UrllibGitHubSink(_config(), opener=opener)

    with pytest.raises(GitHubError) as caught:
        sink.find_issue(title="t", marker="m")
    assert caught.value.code == "malformed_response"
