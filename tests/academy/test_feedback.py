"""Local-first learner feedback, through the real API the browser calls.

Everything here goes through ``create_app`` and the shipped HTTP routes rather
than poking the repository directly. The point of the feature is what a learner
gets when they press a button, and a unit test of the storage class would not
have caught a browser being able to author its own assessment score.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nornyx_lab.academy.app import create_app
from nornyx_lab.academy.feedback import LEARNER_MESSAGES, FeedbackConfiguration
from nornyx_lab.academy.schemas import DestinationVisibility

VALID_MODULE_FEEDBACK = {
    "clarity": 4,
    "confidence": 3,
    "difficulty": "right_level",
    "self_assessment": "understood",
    "comment": "The counters made it click.",
}

VALID_COURSE_FEEDBACK = {
    "overall_clarity": 4,
    "progression": 5,
    "usefulness": 4,
    "final_confidence": 3,
    "overall_difficulty": "right_level",
    "recommend": "yes",
    "most_helpful_module": "F0",
    "most_confusing_module": "09",
    "missing_topic": "More on evidence integrity.",
    "comments": "Good pacing overall.",
}


class RecordingTransport:
    """Counts outbound attempts. Zero is an assertion this feature depends on."""

    def __init__(self, result=None) -> None:
        from nornyx_lab.academy.feedback_client import TransportResult

        self.calls: list[tuple[str, dict]] = []
        self.result = result or TransportResult(ok=True, outcome="created", issue_number=7)

    def send(self, endpoint: str, payload: dict):
        self.calls.append((endpoint, payload))
        return self.result


def _client(tmp_path: Path, *, endpoint: str | None = None, transport=None, **kwargs) -> TestClient:
    return TestClient(
        create_app(
            database_path=tmp_path / "academy.db",
            frontend_dist=tmp_path / "no-frontend-build",
            feedback_configuration=FeedbackConfiguration(
                endpoint=endpoint,
                destination_visibility=kwargs.pop("visibility", DestinationVisibility.UNKNOWN),
            ),
            feedback_transport=transport,
        )
    )


# ------------------------------------------------------------ positive control
def test_a_beginner_can_give_optional_module_feedback_and_it_saves_locally(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/v1/feedback/modules/F0", json=VALID_MODULE_FEEDBACK)
        status = client.get("/api/v1/feedback").json()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["saved"] is True
    assert body["record_id"] >= 1
    record = status["module_feedback"][0]
    assert record["module_id"] == "F0"
    assert record["clarity"] == 4
    assert record["comment"] == "The counters made it click."

    with sqlite3.connect(tmp_path / "academy.db") as connection:
        stored = connection.execute("SELECT COUNT(*) FROM module_feedback").fetchone()[0]
    assert stored == 1, "the rating was not written to the local database"


def test_a_beginner_can_give_optional_course_feedback(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/v1/feedback/course", json=VALID_COURSE_FEEDBACK)
        status = client.get("/api/v1/feedback").json()

    assert response.status_code == 200, response.text
    course = status["course_feedback"]
    assert course["recommend"] == "yes"
    assert course["most_helpful_module"] == "F0"
    assert course["missing_topic"] == "More on evidence integrity."


def test_skipping_feedback_leaves_progress_completely_untouched(tmp_path) -> None:
    """Optional means optional. Never submitting anything is a supported path."""

    with _client(tmp_path) as client:
        run = client.post("/api/v1/modules/F0/run")
        definition = client.app.state.assessments.definition("assessment.F0")
        submitted = client.post(
            "/api/v1/assessments/assessment.F0/submit",
            json={"answers": list(definition.correct)},
        )
        progress = client.get("/api/v1/progress").json()
        status = client.get("/api/v1/feedback").json()

    assert run.status_code == 200 and submitted.status_code == 200
    module = next(item for item in progress["modules"] if item["module_id"] == "F0")
    assert module["status"] == "complete"
    assert status["module_feedback"] == []
    assert status["learner_message"] == LEARNER_MESSAGES["empty"]


def test_learning_works_with_no_network_configured_at_all(tmp_path) -> None:
    """The default installation. Nothing to send to, and nothing broken by it."""

    transport = RecordingTransport()
    with _client(tmp_path, endpoint=None, transport=transport) as client:
        client.post("/api/v1/feedback/modules/F0", json=VALID_MODULE_FEEDBACK)
        client.post("/api/v1/feedback/consent", json={"granted": True})
        status = client.get("/api/v1/feedback").json()

    assert transport.calls == [], "an unconfigured installation attempted a network call"
    assert status["sending_configured"] is False
    assert status["sync"]["status"] == "not_configured"
    assert status["learner_message"] == LEARNER_MESSAGES["not_configured"]
    # The message must read as installation configuration, never as learner error.
    assert "you" not in status["learner_message"].lower().replace("your", "")


# ------------------------------------------------- server-derived context (C)
def test_the_server_derives_assessment_context_the_browser_cannot_state(tmp_path) -> None:
    with _client(tmp_path) as client:
        client.post("/api/v1/modules/F0/run")
        definition = client.app.state.assessments.definition("assessment.F0")
        client.post(
            "/api/v1/assessments/assessment.F0/submit",
            json={"answers": list(definition.correct)},
        )
        client.post("/api/v1/feedback/modules/F0", json=VALID_MODULE_FEEDBACK)
        status = client.get("/api/v1/feedback").json()

    context = status["module_feedback"][0]["academy_context"]
    assert context["module_status"] == "complete"
    assert context["assessment_score"] == 1.0
    assert context["assessment_passed"] is True
    assert context["assessment_attempts"] == 1
    assert context["competence_revision"], "the competence revision was not bound"
    assert context["session_elapsed_seconds"] is not None
    # Every module belongs to more than one authored path and none is recorded,
    # so this stays unknown rather than being invented.
    assert context["learning_path_id"] is None


@pytest.mark.parametrize(
    "forged",
    [
        {"assessment_score": 1.0},
        {"assessment_passed": True},
        {"assessment_attempts": 99},
        {"module_status": "complete"},
        {"competence_revision": "assessment.forged"},
        {"academy_version": "9.9.9"},
        {"nornyx_version": "9.9.9"},
        {"session_id": "11111111-1111-4111-8111-111111111111"},
        {"created_at": "1999-01-01T00:00:00Z"},
        {"learner_id": "someone-else"},
        {"learning_path_id": "beginner"},
        {"academy_context": {"assessment_score": 1.0}},
        {"session_elapsed_seconds": 999999},
    ],
)
def test_a_browser_cannot_author_its_own_academy_context(tmp_path, forged) -> None:
    """The request model has no field for any of this, and forbids extras."""

    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/feedback/modules/F0", json={**VALID_MODULE_FEEDBACK, **forged}
        )
        status = client.get("/api/v1/feedback").json()

    assert response.status_code == 422, response.text
    assert status["module_feedback"] == [], "a rejected submission still stored something"


def test_a_forged_score_is_not_merely_ignored_it_is_refused(tmp_path) -> None:
    """Silently dropping an unexpected field would leave a client believing it worked."""

    with _client(tmp_path) as client:
        # No assessment has been taken, so the honest context is "no attempts".
        response = client.post(
            "/api/v1/feedback/modules/F0",
            json={**VALID_MODULE_FEEDBACK, "assessment_score": 1.0, "assessment_passed": True},
        )
        assert response.status_code == 422

        accepted = client.post("/api/v1/feedback/modules/F0", json=VALID_MODULE_FEEDBACK)
        context = accepted.json()["status"]["module_feedback"][0]["academy_context"]

    assert context["assessment_score"] is None
    assert context["assessment_passed"] is None
    assert context["assessment_attempts"] == 0
    assert context["module_status"] == "not_started"


# ------------------------------------------------------------------ validation
@pytest.mark.parametrize(
    "invalid",
    [
        {"clarity": 0},
        {"clarity": 6},
        {"confidence": -1},
        {"clarity": "four"},
        {"difficulty": "impossible"},
        {"self_assessment": "enlightened"},
        {"comment": "x" * 2001},
    ],
)
def test_out_of_range_perception_is_rejected(tmp_path, invalid) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/feedback/modules/F0", json={**VALID_MODULE_FEEDBACK, **invalid}
        )
    assert response.status_code == 422


def test_feedback_for_an_unknown_module_is_a_clear_404(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/v1/feedback/modules/not-a-module", json=VALID_MODULE_FEEDBACK)
    assert response.status_code == 404
    assert "unknown curriculum module" in response.json()["detail"]


def test_course_feedback_naming_an_unknown_module_is_refused(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/feedback/course",
            json={**VALID_COURSE_FEEDBACK, "most_confusing_module": "../../etc/passwd"},
        )
    assert response.status_code == 422
    assert "unknown curriculum module" in response.json()["detail"]


def test_resubmitting_for_the_same_module_revises_rather_than_duplicating(tmp_path) -> None:
    """One opinion per module per session. A learner changing their mind is a correction."""

    with _client(tmp_path) as client:
        client.post("/api/v1/feedback/modules/F0", json={**VALID_MODULE_FEEDBACK, "clarity": 2})
        client.post("/api/v1/feedback/modules/F0", json={**VALID_MODULE_FEEDBACK, "clarity": 5})
        status = client.get("/api/v1/feedback").json()

    assert len(status["module_feedback"]) == 1
    assert status["module_feedback"][0]["clarity"] == 5


def test_the_comment_is_stored_exactly_as_typed(tmp_path) -> None:
    """Research material. Sanitising the learner's words here would corrupt it.

    Inertness is a rendering property of the gateway, not something achieved by
    editing what someone wrote.
    """

    hostile = "@maintainer ${{ secrets.GITHUB_TOKEN }} <script>x</script> #123 ```fence```"
    with _client(tmp_path) as client:
        client.post(
            "/api/v1/feedback/modules/F0", json={**VALID_MODULE_FEEDBACK, "comment": hostile}
        )
        status = client.get("/api/v1/feedback").json()

    assert status["module_feedback"][0]["comment"] == hostile


# -------------------------------------------------------------------- identity
def test_the_session_identifier_is_a_random_uuid_bound_to_nothing(tmp_path) -> None:
    import uuid

    with _client(tmp_path) as client:
        first = client.get("/api/v1/feedback").json()["session_id"]
        second = client.get("/api/v1/feedback").json()["session_id"]

    parsed = uuid.UUID(first)
    assert parsed.version == 4
    assert first == second, "the session identifier must be stable within a session"


def test_two_installations_do_not_share_a_session_identifier(tmp_path) -> None:
    ids = []
    for name in ("one", "two"):
        directory = tmp_path / name
        directory.mkdir()
        with _client(directory) as client:
            ids.append(client.get("/api/v1/feedback").json()["session_id"])
    assert ids[0] != ids[1]


#: Field names that must not exist anywhere in the transmitted payload. Checked
#: as exact keys rather than substrings: ``learning_path_id`` legitimately
#: contains "path", and a substring test would either fail on it or be quietly
#: weakened to the point of proving nothing.
EXCLUDED_PAYLOAD_KEYS = frozenset(
    {
        "learner_id",
        "learner_name",
        "name",
        "email",
        "github",
        "github_user",
        "hostname",
        "host",
        "username",
        "os_user",
        "user_agent",
        "browser",
        "ip",
        "ip_address",
        "device_id",
        "machine_id",
        "fingerprint",
        "answers",
        "assessment_answers",
        "api_key",
        "token",
        "environment",
        "env",
        "filesystem_path",
        "database_path",
        "cwd",
    }
)


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        found = set(value)
        for item in value.values():
            found |= _all_keys(item)
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for item in value:
            found |= _all_keys(item)
        return found
    return set()


def test_no_identifying_or_device_information_is_recorded(tmp_path) -> None:
    """The exclusion list, checked as keys and as values."""

    import json as _json
    import os
    import socket

    with _client(tmp_path) as client:
        client.post("/api/v1/feedback/modules/F0", json=VALID_MODULE_FEEDBACK)
        client.post("/api/v1/feedback/course", json=VALID_COURSE_FEEDBACK)
        payload = client.app.state.feedback.build_payload(
            client.get("/api/v1/feedback").json()["session_id"]
        )

    present = _all_keys(payload)
    assert not (present & EXCLUDED_PAYLOAD_KEYS), (
        f"the payload carries excluded fields: {sorted(present & EXCLUDED_PAYLOAD_KEYS)}"
    )

    serialized = _json.dumps(payload)
    machine_facts = [
        socket.gethostname(),
        os.environ.get("USERNAME") or os.environ.get("USER") or "\0no-such-user\0",
        str(tmp_path),
    ]
    for fact in machine_facts:
        assert fact and fact not in serialized, f"{fact!r} reached the outbound payload"


def test_the_payload_carries_exactly_the_documented_top_level_sections(tmp_path) -> None:
    """A new section must be a deliberate schema decision, not an accident."""

    with _client(tmp_path) as client:
        client.post("/api/v1/feedback/modules/F0", json=VALID_MODULE_FEEDBACK)
        payload = client.app.state.feedback.build_payload(
            client.get("/api/v1/feedback").json()["session_id"]
        )

    assert set(payload) == {
        "schema_id",
        "session",
        "runtime",
        "module_feedback",
        "course_feedback",
        "sync",
    }
    assert set(payload["session"]) == {
        "session_id",
        "created_at",
        "module_record_count",
        "course_record_count",
    }
    assert set(payload["runtime"]) == {
        "academy_version",
        "nornyx_version",
        "adapter_version",
        "api_version",
        "content_version",
    }


def test_the_stored_row_carries_no_answers_or_credentials(tmp_path) -> None:
    with _client(tmp_path) as client:
        client.post("/api/v1/modules/F0/run")
        definition = client.app.state.assessments.definition("assessment.F0")
        client.post(
            "/api/v1/assessments/assessment.F0/submit",
            json={"answers": list(definition.correct)},
        )
        client.post("/api/v1/feedback/modules/F0", json=VALID_MODULE_FEEDBACK)

    with sqlite3.connect(tmp_path / "academy.db") as connection:
        connection.row_factory = sqlite3.Row
        row = dict(connection.execute("SELECT * FROM module_feedback").fetchone())
    assert "answers" not in row
    for value in row.values():
        for answer in definition.correct:
            assert value != answer
