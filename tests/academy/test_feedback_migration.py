"""Opening a pre-H1 database must not change a single fact about a learner.

The database this test builds is written from literal DDL, not by calling the
code under test. That matters: a migration test that creates its fixture with
the new implementation proves only that the new implementation agrees with
itself. This one reproduces the schema and rows as they exist in a production
store created before H1 existed, then opens it through the real startup path.

What must survive untouched: executions, assessment attempts and their answers,
scores, competence revisions, capstone runs, derived mastery, and advanced
standing. What must not appear: a fabricated feedback record, a fabricated
consent, or a fabricated synchronisation state.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nornyx_lab.academy.app import create_app
from nornyx_lab.academy.feedback import FeedbackConfiguration
from nornyx_lab.academy.schemas import DestinationVisibility

# The schema exactly as a production store carried it at the H1 baseline
# (merge of PR #12): module_progress, assessment_attempts including the
# concepts_tested and competence_revision columns added by earlier migrations,
# and capstone_runs with its competence binding.
PRE_H1_SCHEMA = """
CREATE TABLE module_progress (
    learner_id TEXT NOT NULL,
    module_id TEXT NOT NULL,
    executions INTEGER NOT NULL DEFAULT 0,
    execution_passed INTEGER NOT NULL DEFAULT 0,
    assessment_attempts INTEGER NOT NULL DEFAULT 0,
    assessment_passed INTEGER NOT NULL DEFAULT 0,
    best_score REAL,
    concepts_mastered TEXT NOT NULL DEFAULT '[]',
    concepts_needing_review TEXT NOT NULL DEFAULT '[]',
    version_binding TEXT NOT NULL DEFAULT '{}',
    last_activity TEXT,
    PRIMARY KEY (learner_id, module_id)
);

CREATE TABLE assessment_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    module_id TEXT NOT NULL,
    answers TEXT NOT NULL,
    score REAL NOT NULL,
    passed INTEGER NOT NULL,
    feedback TEXT NOT NULL,
    version_binding TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    concepts_tested TEXT,
    competence_revision TEXT
);

CREATE INDEX idx_assessment_learner_module
    ON assessment_attempts (learner_id, module_id, created_at);

CREATE TABLE capstone_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    scenario TEXT NOT NULL,
    scaffolding TEXT NOT NULL,
    completion_eligible INTEGER NOT NULL,
    learner_authored INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    competence_revision TEXT
);
"""

LEGACY_TABLES = ("module_progress", "assessment_attempts", "capstone_runs")
FEEDBACK_TABLES = (
    "feedback_sessions",
    "feedback_consent_events",
    "module_feedback",
    "course_feedback",
    "feedback_sync_state",
)


def _build_pre_h1_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(PRE_H1_SCHEMA)
        connection.execute(
            """
            INSERT INTO module_progress (
                learner_id, module_id, executions, execution_passed, assessment_attempts,
                assessment_passed, best_score, concepts_mastered, concepts_needing_review,
                version_binding, last_activity
            ) VALUES ('local', 'F0', 3, 1, 2, 1, 1.0, '["evidence"]', '[]',
                      '{"academy": "2.0.0"}', '2026-07-01T09:00:00Z')
            """
        )
        connection.execute(
            """
            INSERT INTO module_progress (
                learner_id, module_id, executions, execution_passed, assessment_attempts,
                assessment_passed, best_score, last_activity
            ) VALUES ('local', '09', 1, 1, 1, 0, 0.5, '2026-07-02T09:00:00Z')
            """
        )
        # A bound attempt that must keep counting, and a legacy unbound one that
        # must keep *not* counting.
        connection.execute(
            """
            INSERT INTO assessment_attempts (
                learner_id, assessment_id, module_id, answers, score, passed, feedback,
                version_binding, created_at, concepts_tested, competence_revision
            ) VALUES ('local', 'assessment.F0', 'F0', ?, 1.0, 1, '[]', '{}',
                      '2026-07-01T09:00:00Z', ?, ?)
            """,
            (
                json.dumps(["a"]),
                json.dumps(["evidence"]),
                _current_assessment_revision(),
            ),
        )
        connection.execute(
            """
            INSERT INTO assessment_attempts (
                learner_id, assessment_id, module_id, answers, score, passed, feedback,
                version_binding, created_at, concepts_tested, competence_revision
            ) VALUES ('local', 'assessment.09', '09', ?, 0.5, 0, '["review"]', '{}',
                      '2026-07-02T09:00:00Z', ?, NULL)
            """,
            (json.dumps(["b"]), json.dumps(["enforcement"])),
        )
        connection.execute(
            """
            INSERT INTO capstone_runs (
                learner_id, run_id, scenario, scaffolding, completion_eligible,
                learner_authored, created_at, competence_revision
            ) VALUES ('local', 'run-legacy', 'customer-remediation', 'guided', 1, 0,
                      '2026-07-03T09:00:00Z', NULL)
            """
        )


def _current_assessment_revision() -> str:
    from nornyx_lab.academy.competence import CompetenceContract, EvidenceFamily

    return CompetenceContract.load().revision(EvidenceFamily.ASSESSMENT)


def _snapshot(path: Path) -> dict[str, list[tuple]]:
    """Every row of every legacy table, ordered deterministically."""

    with sqlite3.connect(path) as connection:
        return {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            for table in LEGACY_TABLES
        }


def _open_through_the_real_startup_path(path: Path, tmp_path: Path) -> TestClient:
    """The production composition root, not a hand-built repository."""

    return TestClient(
        create_app(
            database_path=path,
            frontend_dist=tmp_path / "no-frontend-build",
            feedback_configuration=FeedbackConfiguration(
                endpoint=None, destination_visibility=DestinationVisibility.UNKNOWN
            ),
        )
    )


@pytest.fixture
def pre_h1(tmp_path: Path) -> Path:
    database = tmp_path / "academy.db"
    _build_pre_h1_database(database)
    return database


def test_the_migration_adds_only_feedback_tables(pre_h1, tmp_path) -> None:
    with sqlite3.connect(pre_h1) as connection:
        before = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert not (before & set(FEEDBACK_TABLES))

    with _open_through_the_real_startup_path(pre_h1, tmp_path) as client:
        assert client.get("/api/v1/health").status_code == 200

    with sqlite3.connect(pre_h1) as connection:
        after = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert before <= after, "an existing table disappeared"
    assert set(FEEDBACK_TABLES) <= after
    # Nothing else may appear: an unexpected new table means the migration did
    # more than it was supposed to.
    assert after - before - set(FEEDBACK_TABLES) == set()


def test_using_the_feedback_feature_changes_no_learner_evidence_at_all(pre_h1, tmp_path) -> None:
    """The H1-specific claim, isolated from anything the dashboard does.

    Only feedback endpoints are exercised here — no progress read — so the
    comparison is exact. Every row of every evidence table must be identical
    afterwards, down to the row order.
    """

    before = _snapshot(pre_h1)

    with _open_through_the_real_startup_path(pre_h1, tmp_path) as client:
        client.get("/api/v1/feedback")
        client.post(
            "/api/v1/feedback/modules/F0",
            json={
                "clarity": 5,
                "confidence": 5,
                "difficulty": "too_easy",
                "self_assessment": "understood",
                "comment": "already knew this",
            },
        )
        client.post("/api/v1/feedback/consent", json={"granted": True})
        client.delete("/api/v1/feedback")

    assert _snapshot(pre_h1) == before, "the feedback feature modified learner evidence"


def test_no_pre_existing_row_is_modified_by_opening_the_store(pre_h1, tmp_path) -> None:
    """Migration safety, stated precisely rather than approximately.

    Reading the dashboard materialises an all-zero placeholder row for every
    catalogued module. That is pre-existing behaviour in ``dashboard()`` and is
    unchanged by H1, so the honest assertion is not "the table is identical" —
    it is that no row which already existed is touched, and that anything new is
    an empty placeholder rather than fabricated evidence.
    """

    before = {row[:2]: row for row in _snapshot(pre_h1)["module_progress"]}

    with _open_through_the_real_startup_path(pre_h1, tmp_path) as client:
        client.get("/api/v1/progress")
        client.get("/api/v1/progress/export")
        client.post(
            "/api/v1/feedback/modules/F0",
            json={
                "clarity": 5,
                "confidence": 5,
                "difficulty": "too_easy",
                "self_assessment": "understood",
                "comment": "already knew this",
            },
        )

    after = {row[:2]: row for row in _snapshot(pre_h1)["module_progress"]}
    for key, row in before.items():
        assert after[key] == row, f"pre-existing progress row {key} was modified"

    with sqlite3.connect(pre_h1) as connection:
        connection.row_factory = sqlite3.Row
        for row in connection.execute("SELECT * FROM module_progress"):
            if (row["learner_id"], row["module_id"]) in before:
                continue
            assert row["executions"] == 0
            assert row["assessment_attempts"] == 0
            assert row["assessment_passed"] == 0
            assert row["best_score"] is None
            assert row["last_activity"] is None

    # Attempts and capstone runs are append-only evidence and must not gain a
    # row from any of this.
    with sqlite3.connect(pre_h1) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assessment_attempts").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM capstone_runs").fetchone()[0] == 1


def test_no_feedback_consent_or_sync_state_is_fabricated(pre_h1, tmp_path) -> None:
    """An upgraded installation has given no feedback and consented to nothing."""

    with _open_through_the_real_startup_path(pre_h1, tmp_path) as client:
        status = client.get("/api/v1/feedback").json()

    assert status["module_feedback"] == []
    assert status["course_feedback"] is None
    assert status["consent_state"] == "not_asked"
    assert status["consent_at"] is None
    assert status["sync"]["last_success_at"] is None
    assert status["sync"]["attempts"] == 0
    assert status["sync"]["remote_reference"] is None

    with sqlite3.connect(pre_h1) as connection:
        for table in ("module_feedback", "course_feedback", "feedback_consent_events"):
            count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0, f"{table} was pre-populated by the migration"


def test_prior_competence_reads_exactly_as_it_did_before(pre_h1, tmp_path) -> None:
    """The stale-evidence semantics from PR #12 must survive the upgrade intact."""

    with _open_through_the_real_startup_path(pre_h1, tmp_path) as client:
        dashboard = client.get("/api/v1/progress").json()

    module = next(item for item in dashboard["modules"] if item["module_id"] == "F0")
    assert module["executions"] == 3
    assert module["assessment_attempts"] == 2
    assert module["best_score"] == 1.0
    assert module["status"] == "complete"
    assert "evidence" in module["concepts_mastered"]

    # The unbound legacy capstone run must not have been quietly promoted.
    standing = dashboard["advanced_standing"]
    assert standing["advanced_competence_demonstrated"] is False
    assert standing["independent_authorship_demonstrated"] is False


def test_the_upgraded_store_still_accepts_new_learning(pre_h1, tmp_path) -> None:
    """Positive control: a migrated database is a working database."""

    with _open_through_the_real_startup_path(pre_h1, tmp_path) as client:
        run = client.post("/api/v1/modules/F1/run")
        definition = client.app.state.assessments.definition("assessment.F1")
        submitted = client.post(
            "/api/v1/assessments/assessment.F1/submit",
            json={"answers": list(definition.correct)},
        )
        dashboard = client.get("/api/v1/progress").json()

    assert run.status_code == 200, run.text
    assert submitted.status_code == 200, submitted.text
    module = next(item for item in dashboard["modules"] if item["module_id"] == "F1")
    assert module["status"] == "complete"


def test_opening_the_store_twice_is_idempotent(pre_h1, tmp_path) -> None:
    """Restarts happen. The second start must be a no-op for the schema."""

    with _open_through_the_real_startup_path(pre_h1, tmp_path) as client:
        client.get("/api/v1/feedback")
    with sqlite3.connect(pre_h1) as connection:
        first = connection.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()

    with _open_through_the_real_startup_path(pre_h1, tmp_path) as client:
        client.get("/api/v1/feedback")
    with sqlite3.connect(pre_h1) as connection:
        second = connection.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()

    assert first == second


def test_a_completely_fresh_installation_starts_clean(tmp_path) -> None:
    """The other end of the range: no database at all."""

    database = tmp_path / "nested" / "fresh.db"
    with _open_through_the_real_startup_path(database, tmp_path) as client:
        status = client.get("/api/v1/feedback").json()
        progress = client.get("/api/v1/progress").json()

    assert status["module_feedback"] == []
    assert status["consent_state"] == "not_asked"
    assert progress["completed_modules"] == 0
