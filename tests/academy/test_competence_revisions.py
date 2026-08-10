"""Stale learner evidence must never silently retain standing.

The defect these tests pin down: evidence rows were read forever, with no
record of the semantics they were earned under. A learner who passed an
assessment or completed an Independent capstone kept that standing after the
competence definitions moved, because the row still existed.

Every test here drives the real production learner-record repository — stored
rows in, ``ModuleProgress``/``AdvancedStanding`` out. A helper that classifies
a revision string in isolation would prove nothing about what the academy
reports.
"""

from __future__ import annotations

import sqlite3

import pytest

from nornyx_lab.academy.competence import (
    Admissibility,
    CompetenceContract,
    EvidenceFamily,
    FamilyRule,
)
from nornyx_lab.academy.progress import SQLiteLearnerRecordRepository
from nornyx_lab.academy.schemas import AssessmentResult, ModuleStatus

CAPSTONE_ID = "24"
ASSESSMENT_CONCEPTS = {
    "assessment.MX": ("alpha", "beta"),
    f"assessment.{CAPSTONE_ID}": ("claim register",),
}
MODULE_CONCEPTS = {
    "MX": ("alpha", "beta", "gamma"),
    CAPSTONE_ID: ("claim register",),
}
MODULES = ("MX", CAPSTONE_ID)


def contract(
    *,
    assessment: str = "assessment.r1",
    capstone: str = "capstone.r1",
    assessment_compatible: tuple[str, ...] = (),
    capstone_compatible: tuple[str, ...] = (),
) -> CompetenceContract:
    return CompetenceContract(
        {
            "assessment": FamilyRule(assessment, assessment_compatible),
            "capstone": FamilyRule(capstone, capstone_compatible),
        }
    )


REVISION_ONE = contract()
REVISION_TWO = contract(assessment="assessment.r2", capstone="capstone.r2")
REVISION_TWO_ACCEPTING_ONE = contract(
    assessment="assessment.r2",
    capstone="capstone.r2",
    assessment_compatible=("assessment.r1",),
    capstone_compatible=("capstone.r1",),
)


def repository(path, competence: CompetenceContract) -> SQLiteLearnerRecordRepository:
    return SQLiteLearnerRecordRepository(
        path,
        assessment_concepts=ASSESSMENT_CONCEPTS,
        module_concepts=MODULE_CONCEPTS,
        competence=competence,
    )


def _result(assessment_id: str, module_id: str, concepts: tuple[str, ...]) -> AssessmentResult:
    return AssessmentResult(
        assessment_id=assessment_id,
        module_id=module_id,
        score=1.0,
        passed=True,
        correct_answers=("a",),
        explanation="explanation",
        feedback=("feedback",),
        concepts_mastered=concepts,
        concepts_needing_review=(),
    )


def earn_everything(repo: SQLiteLearnerRecordRepository) -> None:
    """The complete, legitimate path to advanced standing."""

    repo.record_execution("MX", passed=True)
    repo.record_assessment(_result("assessment.MX", "MX", ("alpha", "beta")), answers=("a",))
    repo.record_execution(CAPSTONE_ID, passed=True)
    repo.record_assessment(
        _result(f"assessment.{CAPSTONE_ID}", CAPSTONE_ID, ("claim register",)), answers=("a",)
    )
    repo.record_capstone_run(
        run_id="guided-content",
        scenario="customer-remediation",
        scaffolding="guided",
        completion_eligible=True,
        learner_authored=False,
    )
    repo.record_capstone_run(
        run_id="independent-transfer",
        scenario="refund-disbursement",
        scaffolding="independent",
        completion_eligible=True,
        learner_authored=True,
    )


# --------------------------------------------------------- A. positive control


def test_current_revision_evidence_earns_advanced_standing(tmp_path) -> None:
    """The explicit valid path still works. Without this the gate is just a wall."""

    repo = repository(tmp_path / "learner.db", REVISION_ONE)
    earn_everything(repo)

    dashboard = repo.dashboard(MODULES, capstone_id=CAPSTONE_ID)
    standing = dashboard.advanced_standing
    assert set(dashboard.concepts_mastered) == {"alpha", "beta", "claim register"}
    assert dashboard.concepts_requiring_redemonstration == ()
    assert standing.capstone_content_complete is True
    assert standing.capstone_concepts_demonstrated is True
    assert standing.independent_authorship_demonstrated is True
    assert standing.transfer_demonstrated is True
    assert standing.advanced_competence_demonstrated is True
    assert standing.requires_redemonstration is False


# ------------------------------------------------------- B. stale assessment


def test_stale_assessment_evidence_stops_counting_but_is_retained(tmp_path) -> None:
    db = tmp_path / "learner.db"
    earn_everything(repository(db, REVISION_ONE))

    moved = repository(db, REVISION_TWO)
    progress = moved.get("MX")

    assert progress.concepts_mastered == ()
    assert set(progress.concepts_requiring_redemonstration) == {"alpha", "beta"}
    assert set(progress.concepts_pending_evidence) >= {"alpha", "beta"}
    # The work is still on file; only its present-tense force is withdrawn.
    history = moved.assessment_history()
    assert len(history) == 2
    assert all(item["passed"] for item in history)
    assert {item["competence_admissibility"] for item in history} == {"incompatible"}


def test_stale_assessment_cannot_preserve_advanced_standing(tmp_path) -> None:
    db = tmp_path / "learner.db"
    earn_everything(repository(db, REVISION_ONE))

    # Only the assessment family moves; capstone evidence stays admissible.
    partial = contract(assessment="assessment.r2", capstone="capstone.r1")
    standing = repository(db, partial).dashboard(MODULES, capstone_id=CAPSTONE_ID).advanced_standing

    assert standing.capstone_concepts_demonstrated is False
    assert standing.advanced_competence_demonstrated is False
    assert standing.requires_redemonstration is True
    assert "demonstrated again" in standing.note


# --------------------------------------------------------- C. stale capstone


def test_stale_capstone_runs_do_not_satisfy_independent_or_transfer(tmp_path) -> None:
    db = tmp_path / "learner.db"
    earn_everything(repository(db, REVISION_ONE))

    # Only the capstone family moves; concept evidence stays admissible.
    partial = contract(assessment="assessment.r1", capstone="capstone.r2")
    moved = repository(db, partial)
    standing = moved.dashboard(MODULES, capstone_id=CAPSTONE_ID).advanced_standing

    assert standing.capstone_concepts_demonstrated is True
    assert standing.independent_authorship_demonstrated is False
    assert standing.transfer_demonstrated is False
    assert standing.advanced_competence_demonstrated is False
    assert standing.requires_redemonstration is True

    rows = sqlite3.connect(db).execute("SELECT COUNT(*) FROM capstone_runs").fetchone()[0]
    assert rows == 2, "historical capstone rows must be retained, not deleted"


# ---------------------------------------------- D. mixed-revision composition


@pytest.mark.parametrize(
    ("stale_family", "expected_note_fragment"),
    [
        ("assessment", "capstone concept evidence"),
        ("capstone", "independent authorship"),
    ],
)
def test_no_mixture_of_current_and_stale_evidence_fabricates_standing(
    tmp_path, stale_family: str, expected_note_fragment: str
) -> None:
    """Half-current evidence is not standing. Every required item must be admissible."""

    db = tmp_path / "learner.db"
    earn_everything(repository(db, REVISION_ONE))
    moved = contract(
        assessment="assessment.r2" if stale_family == "assessment" else "assessment.r1",
        capstone="capstone.r2" if stale_family == "capstone" else "capstone.r1",
    )

    standing = repository(db, moved).dashboard(MODULES, capstone_id=CAPSTONE_ID).advanced_standing

    assert standing.advanced_competence_demonstrated is False
    assert expected_note_fragment in standing.note


def test_stale_independent_plus_fresh_transfer_still_fails(tmp_path) -> None:
    """Re-earning only part of the capstone evidence does not restore the rest."""

    db = tmp_path / "learner.db"
    earn_everything(repository(db, REVISION_ONE))

    moved = repository(db, REVISION_TWO)
    # The learner redoes only the transfer scenario under the new semantics.
    moved.record_capstone_run(
        run_id="transfer-redone",
        scenario="refund-disbursement",
        scaffolding="reduced",
        completion_eligible=True,
        learner_authored=True,
    )
    standing = moved.dashboard(MODULES, capstone_id=CAPSTONE_ID).advanced_standing

    assert standing.transfer_demonstrated is True
    assert standing.independent_authorship_demonstrated is False
    assert standing.advanced_competence_demonstrated is False


def test_evidence_from_several_superseded_revisions_never_accumulates(tmp_path) -> None:
    db = tmp_path / "learner.db"
    earn_everything(repository(db, REVISION_ONE))
    second = contract(assessment="assessment.r2", capstone="capstone.r2")
    earn_everything(repository(db, second))

    third = contract(assessment="assessment.r3", capstone="capstone.r3")
    standing = repository(db, third).dashboard(MODULES, capstone_id=CAPSTONE_ID).advanced_standing

    assert standing.independent_authorship_demonstrated is False
    assert standing.transfer_demonstrated is False
    assert standing.advanced_competence_demonstrated is False


# ------------------------------------------------------ E. legacy unbound rows


def _legacy_database(path) -> None:
    """A store written before evidence carried any competence binding."""

    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE module_progress (
                learner_id TEXT NOT NULL, module_id TEXT NOT NULL,
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
                learner_id TEXT NOT NULL, assessment_id TEXT NOT NULL,
                module_id TEXT NOT NULL, answers TEXT NOT NULL,
                score REAL NOT NULL, passed INTEGER NOT NULL,
                feedback TEXT NOT NULL,
                version_binding TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE capstone_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                learner_id TEXT NOT NULL, run_id TEXT NOT NULL,
                scenario TEXT NOT NULL, scaffolding TEXT NOT NULL,
                completion_eligible INTEGER NOT NULL,
                learner_authored INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO module_progress (learner_id, module_id, executions, execution_passed,"
            " assessment_attempts, assessment_passed, best_score, concepts_mastered,"
            " last_activity) VALUES ('local', ?, 1, 1, 1, 1, 1.0, ?, '2026-01-01T00:00:00Z')",
            [("MX", '["alpha", "beta"]'), (CAPSTONE_ID, '["claim register"]')],
        )
        connection.executemany(
            "INSERT INTO assessment_attempts (learner_id, assessment_id, module_id, answers,"
            " score, passed, feedback, version_binding, created_at)"
            " VALUES ('local', ?, ?, '[]', 1.0, 1, '[]', '{\"academy\": \"2.0.0\"}',"
            " '2026-01-01T00:00:00Z')",
            [("assessment.MX", "MX"), (f"assessment.{CAPSTONE_ID}", CAPSTONE_ID)],
        )
        connection.execute(
            "INSERT INTO capstone_runs (learner_id, run_id, scenario, scaffolding,"
            " completion_eligible, learner_authored, created_at)"
            " VALUES ('local', 'legacy-independent', 'refund-disbursement', 'independent',"
            " 1, 1, '2026-01-01T00:00:00Z')"
        )


def test_legacy_unbound_database_migrates_without_granting_standing(tmp_path) -> None:
    db = tmp_path / "legacy.db"
    _legacy_database(db)

    repo = repository(db, REVISION_ONE)  # must not raise
    dashboard = repo.dashboard(MODULES, capstone_id=CAPSTONE_ID)
    standing = dashboard.advanced_standing

    # Rows survive, and no revision is invented for them.
    with sqlite3.connect(db) as connection:
        attempts = connection.execute(
            "SELECT competence_revision FROM assessment_attempts"
        ).fetchall()
        runs = connection.execute("SELECT competence_revision FROM capstone_runs").fetchall()
    assert len(attempts) == 2 and all(row[0] is None for row in attempts)
    assert len(runs) == 1 and runs[0][0] is None

    # The activity is still visible; the competence claim is not.
    assert dashboard.modules[0].status is ModuleStatus.COMPLETE
    assert dashboard.concepts_mastered == ()
    assert set(dashboard.concepts_requiring_redemonstration) == {
        "alpha",
        "beta",
        "claim register",
    }
    assert standing.independent_authorship_demonstrated is False
    assert standing.advanced_competence_demonstrated is False
    assert standing.requires_redemonstration is True
    assert "demonstrated again" in standing.note


def test_unbound_evidence_is_classified_unbound_not_merely_unknown() -> None:
    assert REVISION_ONE.admits(EvidenceFamily.ASSESSMENT, None) is Admissibility.UNBOUND
    assert REVISION_ONE.admits(EvidenceFamily.ASSESSMENT, "") is Admissibility.UNBOUND
    assert Admissibility.UNBOUND.admissible is False


# ------------------------------------------------- F. explicit compatibility


def test_explicitly_compatible_prior_revision_still_counts(tmp_path) -> None:
    db = tmp_path / "learner.db"
    earn_everything(repository(db, REVISION_ONE))

    standing = (
        repository(db, REVISION_TWO_ACCEPTING_ONE)
        .dashboard(MODULES, capstone_id=CAPSTONE_ID)
        .advanced_standing
    )

    assert standing.advanced_competence_demonstrated is True
    assert standing.requires_redemonstration is False


def test_compatibility_is_explicit_and_never_inferred(tmp_path) -> None:
    """Not from ordering, recency, package version, or name similarity."""

    db = tmp_path / "learner.db"
    earn_everything(repository(db, REVISION_ONE))

    lookalikes = (
        contract(assessment="assessment.r1 ", capstone="capstone.r1 "),  # whitespace
        contract(assessment="assessment.R1", capstone="capstone.R1"),  # case
        contract(assessment="assessment.r10", capstone="capstone.r10"),  # prefix
        contract(assessment="assessment.r0", capstone="capstone.r0"),  # earlier
    )
    for moved in lookalikes:
        standing = (
            repository(db, moved).dashboard(MODULES, capstone_id=CAPSTONE_ID).advanced_standing
        )
        assert standing.advanced_competence_demonstrated is False

    # Declaring compatibility for the *other* family does not help either.
    crossed = contract(
        assessment="assessment.r2",
        capstone="capstone.r2",
        assessment_compatible=("capstone.r1",),
        capstone_compatible=("assessment.r1",),
    )
    crossed_standing = (
        repository(db, crossed).dashboard(MODULES, capstone_id=CAPSTONE_ID).advanced_standing
    )
    assert crossed_standing.advanced_competence_demonstrated is False


def test_contract_rejects_self_referential_compatibility() -> None:
    with pytest.raises(ValueError, match="own revision"):
        CompetenceContract(
            {"assessment": FamilyRule("r1", ("r1",)), "capstone": FamilyRule("c1")}
        ).admits("assessment", "r1")


# --------------------------------------------------------- G. revision change


def test_same_rows_flip_to_stale_when_only_the_contract_moves(tmp_path) -> None:
    """Proves compatibility is evaluated, not merely stored.

    Nothing about the learner's rows changes between these two reads — the
    bytes on disk are identical. Only the contract differs.
    """

    db = tmp_path / "learner.db"
    earn_everything(repository(db, REVISION_ONE))

    def snapshot() -> list[tuple]:
        with sqlite3.connect(db) as connection:
            return connection.execute(
                "SELECT id, passed, competence_revision FROM assessment_attempts ORDER BY id"
            ).fetchall()

    before_rows = snapshot()
    before = repository(db, REVISION_ONE).dashboard(MODULES, capstone_id=CAPSTONE_ID)
    after = repository(db, REVISION_TWO).dashboard(MODULES, capstone_id=CAPSTONE_ID)
    after_rows = snapshot()

    assert before_rows == after_rows, "evaluating compatibility must not rewrite history"
    assert before.advanced_standing.advanced_competence_demonstrated is True
    assert after.advanced_standing.advanced_competence_demonstrated is False


# ------------------------------------------------------ H. restart/persistence


def test_semantics_survive_repository_reconstruction(tmp_path) -> None:
    db = tmp_path / "learner.db"
    earn_everything(repository(db, REVISION_ONE))
    del_repo = repository(db, REVISION_ONE)
    assert del_repo.dashboard(
        MODULES, capstone_id=CAPSTONE_ID
    ).advanced_standing.advanced_competence_demonstrated

    # Fresh objects, fresh connections, same file — the binding is on the row.
    for _ in range(3):
        rebuilt = repository(db, REVISION_TWO)
        assert (
            rebuilt.dashboard(
                MODULES, capstone_id=CAPSTONE_ID
            ).advanced_standing.advanced_competence_demonstrated
            is False
        )
    restored = repository(db, REVISION_ONE)
    assert (
        restored.dashboard(
            MODULES, capstone_id=CAPSTONE_ID
        ).advanced_standing.advanced_competence_demonstrated
        is True
    )


def test_replayed_duplicate_rows_do_not_create_standing(tmp_path) -> None:
    """Copying a stale row many times is still stale evidence."""

    db = tmp_path / "learner.db"
    earn_everything(repository(db, REVISION_ONE))
    with sqlite3.connect(db) as connection:
        connection.executescript(
            """
            INSERT INTO capstone_runs (learner_id, run_id, scenario, scaffolding,
                completion_eligible, learner_authored, created_at, competence_revision)
            SELECT learner_id, run_id || '-replay', scenario, scaffolding,
                completion_eligible, learner_authored, created_at, competence_revision
            FROM capstone_runs;
            INSERT INTO assessment_attempts (learner_id, assessment_id, module_id, answers,
                score, passed, feedback, version_binding, created_at, concepts_tested,
                competence_revision)
            SELECT learner_id, assessment_id, module_id, answers, score, passed, feedback,
                version_binding, created_at, concepts_tested, competence_revision
            FROM assessment_attempts;
            """
        )

    standing = (
        repository(db, REVISION_TWO).dashboard(MODULES, capstone_id=CAPSTONE_ID).advanced_standing
    )
    assert standing.advanced_competence_demonstrated is False


def test_forged_or_malformed_revisions_are_rejected(tmp_path) -> None:
    db = tmp_path / "learner.db"
    earn_everything(repository(db, REVISION_ONE))
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE capstone_runs SET competence_revision = 'capstone.r99-forged'")
        connection.execute("UPDATE assessment_attempts SET competence_revision = '{}'")

    standing = (
        repository(db, REVISION_ONE).dashboard(MODULES, capstone_id=CAPSTONE_ID).advanced_standing
    )
    assert standing.independent_authorship_demonstrated is False
    assert standing.capstone_concepts_demonstrated is False
    assert standing.advanced_competence_demonstrated is False


# ------------------------------------------------------------- I. reset


def test_reset_clears_bound_evidence_without_leaving_residue(tmp_path) -> None:
    db = tmp_path / "learner.db"
    repo = repository(db, REVISION_ONE)
    earn_everything(repo)
    repo.reset()

    dashboard = repo.dashboard(MODULES, capstone_id=CAPSTONE_ID)
    assert dashboard.completed_modules == 0
    assert dashboard.concepts_mastered == ()
    assert dashboard.concepts_requiring_redemonstration == ()
    assert dashboard.advanced_standing.advanced_competence_demonstrated is False
    assert dashboard.advanced_standing.requires_redemonstration is False
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM capstone_runs").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM assessment_attempts").fetchone()[0] == 0

    # And the learner can earn standing again from a clean record.
    earn_everything(repo)
    assert (
        repo.dashboard(
            MODULES, capstone_id=CAPSTONE_ID
        ).advanced_standing.advanced_competence_demonstrated
        is True
    )


# ----------------------------------------------------------- contract safety


def test_unknown_family_fails_closed() -> None:
    assert REVISION_ONE.admits("mystery", "anything") is Admissibility.INCOMPATIBLE
    with pytest.raises(KeyError):
        REVISION_ONE.revision("mystery")


def test_loaded_contract_declares_every_family_the_code_records() -> None:
    loaded = CompetenceContract.load()
    for family in EvidenceFamily:
        assert loaded.revision(family)
        assert loaded.declared_digest(family).startswith("sha256:")


# ------------------------------------------- real API wiring, not just helpers


def test_live_api_stamps_the_real_contract_and_exposes_redemonstration(tmp_path) -> None:
    """The production app must bind evidence and surface the honest reason.

    Exercises the shipped wiring end to end: FastAPI -> catalog/assessment
    services -> the real learner repository -> the JSON a browser receives.
    """

    from fastapi.testclient import TestClient

    from nornyx_lab.academy.app import create_app
    from nornyx_lab.academy.assessments import AssessmentService

    client = TestClient(create_app(database_path=tmp_path / "api.db", frontend_dist=tmp_path))
    definition = AssessmentService().definition("assessment.F0")
    submitted = client.post(
        "/api/v1/assessments/assessment.F0/submit",
        json={"answers": list(definition.correct)},
    )
    assert submitted.status_code == 200 and submitted.json()["passed"] is True

    live = CompetenceContract.load()
    exported = client.get("/api/v1/progress/export").json()
    attempt = exported["assessment_history"][0]
    assert attempt["competence_revision"] == live.revision(EvidenceFamily.ASSESSMENT)
    assert attempt["competence_admissibility"] == "current"

    progress = client.get("/api/v1/progress").json()
    assert set(progress["concepts_mastered"]) == set(definition.concepts)
    assert progress["concepts_requiring_redemonstration"] == []
    assert progress["advanced_standing"]["requires_redemonstration"] is False

    # Now move the semantics under the same rows, using the same production
    # repository class the app builds, and read the learner-facing result.
    moved = SQLiteLearnerRecordRepository(
        tmp_path / "api.db",
        assessment_concepts={"assessment.F0": definition.concepts},
        module_concepts={"F0": definition.concepts},
        competence=contract(assessment="assessment.moved", capstone="capstone.moved"),
    )
    after = moved.dashboard(("F0",), capstone_id=CAPSTONE_ID)
    assert after.concepts_mastered == ()
    assert set(after.concepts_requiring_redemonstration) == set(definition.concepts)
