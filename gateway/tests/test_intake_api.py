"""API-level behaviour of the intake service, through the real ASGI app."""

from __future__ import annotations

import json

import pytest
from conftest import SESSION_ID, FakeGitHub, digest_of, make_payload
from fastapi.testclient import TestClient

from nornyx_feedback_gateway.app import create_app
from nornyx_feedback_gateway.config import GatewayConfig
from nornyx_feedback_gateway.github import GitHubError

TOKEN = "ghp-test-token-value-never-echoed"


def client(config: GatewayConfig, sink: FakeGitHub | None = None) -> TestClient:
    return TestClient(create_app(config=config, sink=sink))


# ------------------------------------------------------------------ positive
def test_health_reports_configuration_without_revealing_the_credential(config) -> None:
    with client(config) as api:
        response = api.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["github_configured"] is True
    assert body["destination_visibility"] == "private"
    assert TOKEN not in response.text
    # The intake repository is deployment detail, not something an unauthenticated
    # caller gets to enumerate.
    assert "nornyx-lab-feedback-intake" not in response.text


def test_a_valid_payload_creates_exactly_one_issue(config, sink) -> None:
    with client(config, sink) as api:
        response = api.post("/v1/feedback", json=make_payload())

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "created"
    assert body["issue_number"] == 1
    assert body["destination_visibility"] == "private"
    assert len(sink.issues) == 1
    assert sink.issues[1]["title"] == "[Learner Feedback] Session 7f21ac1e"


def test_the_same_payload_twice_does_not_create_a_second_issue(config, sink) -> None:
    payload = make_payload()
    with client(config, sink) as api:
        first = api.post("/v1/feedback", json=payload)
        second = api.post("/v1/feedback", json=payload)

    assert first.json()["status"] == "created"
    assert second.json()["status"] == "unchanged"
    assert second.json()["issue_number"] == first.json()["issue_number"]
    assert len(sink.issues) == 1
    # An unchanged payload must not even touch the issue: a no-op edit still
    # writes a timeline entry, so a retrying client would spam the record.
    assert [call for call in sink.calls if call[0] == "update"] == []


def test_a_changed_payload_updates_the_same_issue(config, sink) -> None:
    with client(config, sink) as api:
        first = api.post("/v1/feedback", json=make_payload(clarity=4))
        second = api.post("/v1/feedback", json=make_payload(clarity=2))

    assert first.json()["status"] == "created"
    assert second.json()["status"] == "updated"
    assert second.json()["issue_number"] == first.json()["issue_number"]
    assert len(sink.issues) == 1
    assert "| 2 |" in sink.issues[1]["body"]


def test_a_restarted_gateway_updates_the_issue_it_no_longer_remembers(
    config, sink, tmp_path
) -> None:
    """The gateway's own store is a cache, not the authority.

    GitHub is. A gateway that lost its database — redeployed, moved, ephemeral
    volume — must recover the session's issue rather than open a second one.
    """

    with client(config, sink) as api:
        first = api.post("/v1/feedback", json=make_payload(clarity=4))

    restarted = GatewayConfig(
        github_repository=config.github_repository,
        github_token=config.github_token,
        database_path=str(tmp_path / "fresh-after-restart.db"),
        destination_visibility="private",
    )
    with client(restarted, sink) as api:
        second = api.post("/v1/feedback", json=make_payload(clarity=1))

    assert first.json()["status"] == "created"
    assert second.json()["status"] == "updated"
    assert second.json()["issue_number"] == first.json()["issue_number"]
    assert len(sink.issues) == 1


def test_an_ambiguous_timeout_after_the_remote_create_does_not_duplicate(config, sink) -> None:
    """The failure that makes naive retry logic produce two issues.

    The issue is written on GitHub and then the response is lost. The client
    sees a failure and retries. Recovery has to find the issue that already
    exists, because nothing local knows about it.
    """

    sink.create_then_fail = GitHubError("timeout", "response lost after the write")
    with client(config, sink) as api:
        lost = api.post("/v1/feedback", json=make_payload())
        assert lost.status_code == 503
        assert lost.json()["code"] == "timeout"
        assert len(sink.issues) == 1  # GitHub really did create it

        retry = api.post("/v1/feedback", json=make_payload())

    assert retry.status_code == 202, retry.text
    assert retry.json()["status"] == "updated"
    assert retry.json()["issue_number"] == 1
    assert len(sink.issues) == 1


# ------------------------------------------------------------------ negative
@pytest.mark.parametrize(
    ("code", "status", "expected"),
    [
        ("unauthorized", 401, 502),
        ("forbidden", 403, 502),
        ("not_found", 404, 502),
        ("rejected", 422, 502),
        ("server_error", 500, 503),
        ("timeout", None, 503),
        ("unreachable", None, 503),
        ("malformed_response", None, 502),
    ],
)
def test_every_github_failure_is_reported_as_a_code_without_leaking_detail(
    config, sink, code, status, expected
) -> None:
    sink.fail_on["create_issue"] = GitHubError(code, f"raw upstream text {TOKEN}", status=status)
    with client(config, sink) as api:
        response = api.post("/v1/feedback", json=make_payload())

    assert response.status_code == expected
    assert response.json()["code"] == code
    assert TOKEN not in response.text
    assert "raw upstream text" not in response.text
    assert "nornyx-lab-feedback-intake" not in response.text
    assert "Traceback" not in response.text


def test_an_unconfigured_destination_refuses_rather_than_writing_anywhere(tmp_path, sink) -> None:
    unconfigured = GatewayConfig(database_path=str(tmp_path / "gateway.db"))
    with client(unconfigured, sink) as api:
        response = api.post("/v1/feedback", json=make_payload())

    assert response.status_code == 503
    assert response.json()["code"] == "github_not_configured"
    assert sink.calls == []


@pytest.mark.parametrize(
    "mutation",
    [
        {"session": {"session_id": "not-a-uuid"}},
        {"module_feedback": [{"perception": {"clarity": 6}}]},
        {"module_feedback": [{"perception": {"clarity": 0}}]},
        {"module_feedback": [{"perception": {"difficulty": "impossible"}}]},
        {"module_feedback": [{"perception": {"self_assessment": "enlightened"}}]},
        {"module_feedback": [{"module_id": "../../etc/passwd"}]},
        {"module_feedback": [{"module_id": "a`b"}]},
        {"schema_id": "nornyx.academy.learner_feedback.v2"},
        {"course_feedback": {"perception": {"recommend": "absolutely"}}},
        {"course_feedback": {"perception": {"most_helpful_module": "not a module id"}}},
        {"sync": {"payload_digest": "md5:abc"}},
    ],
)
def test_malformed_payloads_are_rejected_and_never_reach_github(config, sink, mutation) -> None:
    payload = make_payload()
    for key, value in mutation.items():
        if key == "module_feedback":
            for section, fields in value[0].items():
                if isinstance(fields, dict):
                    payload["module_feedback"][0][section].update(fields)
                else:
                    payload["module_feedback"][0][section] = fields
        elif key == "course_feedback":
            payload["course_feedback"]["perception"].update(value["perception"])
        elif isinstance(value, dict):
            payload[key].update(value)
        else:
            payload[key] = value

    with client(config, sink) as api:
        response = api.post("/v1/feedback", json=payload)

    assert response.status_code == 422, response.text
    assert sink.calls == []


def test_unknown_fields_are_refused_rather_than_ignored(config, sink) -> None:
    payload = make_payload()
    payload["module_feedback"][0]["perception"]["secret_admin_flag"] = True

    with client(config, sink) as api:
        response = api.post("/v1/feedback", json=payload)

    assert response.status_code == 422
    assert sink.calls == []


def test_an_oversized_body_is_refused_before_it_is_parsed(tmp_path, sink) -> None:
    small = GatewayConfig(
        github_repository="owner/name",
        github_token=TOKEN,
        database_path=str(tmp_path / "gateway.db"),
        max_body_bytes=2048,
    )
    payload = make_payload(comment="x" * 1900)
    oversized = json.dumps(payload)
    assert len(oversized) > 2048

    with client(small, sink) as api:
        response = api.post(
            "/v1/feedback", content=oversized, headers={"content-type": "application/json"}
        )

    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"
    assert sink.calls == []


def test_a_flood_of_requests_is_rate_limited(tmp_path, sink) -> None:
    limited = GatewayConfig(
        github_repository="owner/name",
        github_token=TOKEN,
        database_path=str(tmp_path / "gateway.db"),
        rate_limit_per_minute=2,
    )
    with client(limited, sink) as api:
        statuses = [
            api.post(
                "/v1/feedback", json=make_payload(session_id=f"{n:08x}-0000-4000-8000-000000000000")
            ).status_code
            for n in range(4)
        ]

    assert statuses[:2] == [202, 202]
    assert statuses[2:] == [429, 429]


def test_a_long_comment_beyond_the_bound_is_rejected(config, sink) -> None:
    payload = make_payload(comment="a" * 2001)
    payload["sync"]["payload_digest"] = digest_of(payload)

    with client(config, sink) as api:
        response = api.post("/v1/feedback", json=payload)

    assert response.status_code == 422
    assert sink.calls == []


def test_the_credential_never_appears_in_any_response(config, sink) -> None:
    with client(config, sink) as api:
        responses = [
            api.get("/health"),
            api.post("/v1/feedback", json=make_payload()),
            api.post("/v1/feedback", json={"schema_id": "wrong"}),
            api.get("/v1/feedback"),
        ]

    for response in responses:
        assert TOKEN not in response.text
        assert "Authorization" not in response.text


def test_the_service_exposes_no_documentation_or_schema_surface(config, sink) -> None:
    """Nothing here should advertise itself to a scanner."""

    with client(config, sink) as api:
        assert api.get("/openapi.json").status_code == 404
        assert api.get("/docs").status_code == 404


def test_session_identity_is_the_only_thing_that_groups_records(config, sink) -> None:
    other = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    with client(config, sink) as api:
        first = api.post("/v1/feedback", json=make_payload(session_id=SESSION_ID))
        second = api.post("/v1/feedback", json=make_payload(session_id=other))

    assert first.json()["issue_number"] != second.json()["issue_number"]
    assert len(sink.issues) == 2
