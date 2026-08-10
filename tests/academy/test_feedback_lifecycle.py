"""Deletion, reset independence, and the maintainer summary.

Two behaviours here are decisions a reviewer should be able to see stated
rather than infer:

* **Resetting progress does not delete feedback, and deleting feedback does not
  reset progress.** They are different things a learner might want, and quietly
  coupling them would destroy research data as a side effect of "start over".
* **Deleting a local copy is not a remote deletion.** Where something has
  already been sent, the product says so instead of implying it has been
  recalled.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from nornyx_lab.academy.app import create_app
from nornyx_lab.academy.feedback import FeedbackConfiguration
from nornyx_lab.academy.feedback_client import TransportResult
from nornyx_lab.academy.schemas import DestinationVisibility

FEEDBACK = {
    "clarity": 4,
    "confidence": 2,
    "difficulty": "too_hard",
    "self_assessment": "partly_understood",
    "comment": "the middle section moved fast",
}

COURSE = {
    "overall_clarity": 3,
    "progression": 4,
    "usefulness": 5,
    "final_confidence": 3,
    "overall_difficulty": "right_level",
    "recommend": "maybe",
}


class AcceptingTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def send(self, endpoint: str, payload: dict) -> TransportResult:
        self.calls.append((endpoint, payload))
        return TransportResult(ok=True, outcome="created", issue_number=5)


def _client(tmp_path: Path, *, endpoint: str | None = None, transport=None) -> TestClient:
    return TestClient(
        create_app(
            database_path=tmp_path / "academy.db",
            frontend_dist=tmp_path / "no-frontend-build",
            feedback_configuration=FeedbackConfiguration(
                endpoint=endpoint, destination_visibility=DestinationVisibility.PRIVATE
            ),
            feedback_transport=transport,
        )
    )


def _complete_a_module(client: TestClient, module_id: str = "F0") -> None:
    client.post(f"/api/v1/modules/{module_id}/run")
    definition = client.app.state.assessments.definition(f"assessment.{module_id}")
    client.post(
        f"/api/v1/assessments/assessment.{module_id}/submit",
        json={"answers": list(definition.correct)},
    )


# ---------------------------------------------------------------- independence
def test_resetting_progress_keeps_feedback(tmp_path) -> None:
    with _client(tmp_path) as client:
        _complete_a_module(client)
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        client.post("/api/v1/feedback/course", json=COURSE)

        reset = client.post("/api/v1/progress/reset")
        status = client.get("/api/v1/feedback").json()

    assert reset.status_code == 200
    assert reset.json()["completed_modules"] == 0
    assert len(status["module_feedback"]) == 1, "resetting progress silently destroyed feedback"
    assert status["course_feedback"] is not None
    # The context captured at submission time is a record of what was true then,
    # and a later reset does not rewrite history.
    assert status["module_feedback"][0]["academy_context"]["module_status"] == "complete"


def test_deleting_feedback_keeps_progress(tmp_path) -> None:
    with _client(tmp_path) as client:
        _complete_a_module(client)
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)

        deleted = client.delete("/api/v1/feedback").json()
        progress = client.get("/api/v1/progress").json()

    assert deleted["deleted_module_records"] == 1
    module = next(item for item in progress["modules"] if item["module_id"] == "F0")
    assert module["status"] == "complete"
    assert progress["concepts_mastered"]


def test_deletion_removes_every_local_feedback_row(tmp_path) -> None:
    """Nothing of the deleted feedback survives — content, consent, or sync state.

    A fresh empty session does remain, because the learner is still using the
    academy and may give feedback again. What matters is that it carries none of
    what was deleted: no records, no consent, no delivery history.
    """

    with _client(tmp_path) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        client.post("/api/v1/feedback/course", json=COURSE)
        client.post("/api/v1/feedback/consent", json={"granted": True})
        before = client.get("/api/v1/feedback").json()["session_id"]
        client.delete("/api/v1/feedback")

    with sqlite3.connect(tmp_path / "academy.db") as connection:
        connection.row_factory = sqlite3.Row
        for table in ("module_feedback", "course_feedback", "feedback_consent_events"):
            count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0, f"{table} still holds rows after deletion"

        sessions = connection.execute("SELECT * FROM feedback_sessions").fetchall()
        assert len(sessions) == 1
        remaining = sessions[0]
        assert remaining["session_id"] != before
        assert remaining["consent_state"] == "not_asked"
        assert remaining["consent_at"] is None

        sync = connection.execute("SELECT * FROM feedback_sync_state").fetchall()
        assert len(sync) == 1
        assert sync[0]["session_id"] == remaining["session_id"]
        assert sync[0]["synced_digest"] is None
        assert sync[0]["attempts"] == 0


def test_deletion_starts_a_new_session_rather_than_resurrecting_consent(tmp_path) -> None:
    transport = AcceptingTransport()
    with _client(tmp_path, endpoint="https://gateway.test/v1/feedback", transport=transport) as c:
        c.post("/api/v1/feedback/consent", json={"granted": True})
        c.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        first = c.get("/api/v1/feedback").json()["session_id"]

        c.delete("/api/v1/feedback")
        after = c.get("/api/v1/feedback").json()

    assert after["session_id"] != first, "deletion reused the identifier of erased feedback"
    assert after["consent_state"] == "not_asked", "consent survived the deletion of its session"
    assert after["sync"]["remote_reference"] is None


def test_deleting_locally_never_claims_a_remote_deletion(tmp_path) -> None:
    transport = AcceptingTransport()
    with _client(tmp_path, endpoint="https://gateway.test/v1/feedback", transport=transport) as c:
        c.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        c.post("/api/v1/feedback/consent", json={"granted": True})
        assert c.get("/api/v1/feedback").json()["sync"]["status"] == "synced"

        deleted = c.delete("/api/v1/feedback").json()

    assert deleted["previously_submitted_externally"] is True
    limitation = deleted["limitation"].lower()
    assert "does not remove" in limitation
    for overclaim in ("deleted from", "erased everywhere", "removed from the maintainers"):
        assert overclaim not in limitation


def test_deleting_feedback_that_was_never_sent_says_nothing_about_removal(tmp_path) -> None:
    with _client(tmp_path) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        deleted = client.delete("/api/v1/feedback").json()

    assert deleted["previously_submitted_externally"] is False
    assert deleted["limitation"] == ""


def test_deleting_when_there_is_nothing_to_delete_is_not_an_error(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.delete("/api/v1/feedback")

    assert response.status_code == 200
    assert response.json()["deleted_module_records"] == 0


# --------------------------------------------------------------------- summary
def test_the_summary_always_reports_its_sample_size(tmp_path) -> None:
    with _client(tmp_path) as client:
        client.post(
            "/api/v1/feedback/modules/F0",
            json={**FEEDBACK, "clarity": 2, "confidence": 5},
        )
        client.post("/api/v1/feedback/course", json=COURSE)
        summary = client.get("/api/v1/feedback/summary").json()

    module = summary["modules"][0]
    assert module["module_id"] == "F0"
    assert module["sample_count"] == 1
    assert module["average_clarity"] == 2.0
    assert module["difficulty_distribution"] == {"too_hard": 1}
    assert module["understanding_distribution"] == {"partly_understood": 1}
    assert summary["course"]["sample_count"] == 1
    assert summary["course"]["recommendation_distribution"] == {"maybe": 1}


def test_the_summary_states_that_it_supports_no_causal_conclusion(tmp_path) -> None:
    with _client(tmp_path) as client:
        summary = client.get("/api/v1/feedback/summary").json()

    limit = summary["interpretation_limit"].lower()
    assert "not measurements of teaching quality" in limit
    assert "no causal conclusion" in limit


def test_a_confident_learner_who_failed_is_counted_as_a_signal_not_a_verdict(tmp_path) -> None:
    """The mismatch counter exists to prompt a look, never to conclude anything."""

    with _client(tmp_path) as client:
        client.post("/api/v1/modules/F0/run")
        client.post("/api/v1/assessments/assessment.F0/submit", json={"answers": ["zzz"]})
        client.post(
            "/api/v1/feedback/modules/F0",
            json={**FEEDBACK, "confidence": 5, "self_assessment": "understood"},
        )
        summary = client.get("/api/v1/feedback/summary").json()

    module = summary["modules"][0]
    assert module["assessment_pass_rate"] == 0.0
    assert module["confidence_pass_mismatch"] == 1
    assert module["sample_count"] == 1


def test_an_empty_installation_reports_zero_rather_than_a_fabricated_average(tmp_path) -> None:
    with _client(tmp_path) as client:
        summary = client.get("/api/v1/feedback/summary").json()

    assert summary["modules"] == []
    assert summary["course"]["sample_count"] == 0
    assert summary["course"]["average_overall_clarity"] is None
