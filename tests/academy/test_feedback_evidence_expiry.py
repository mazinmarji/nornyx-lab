"""Feedback context must obey evidence expiry, not route around it.

The defect these tests pin down: feedback context read
``module_progress.best_score`` and ``module_progress.assessment_passed`` — the
lifetime aggregates — and stamped them with the *current* competence revision.
That pairing is a false claim. The aggregate remembers every attempt ever made
with no memory of the semantics each was earned under, so a pass from a
superseded revision would be published as an assessment result under a revision
it was never earned under, in a research record, alongside a rating.

PR #12 established the rule for competence: evidence payload + the revision it
was earned under + the current compatibility rule → admissible evidence.
Feedback context is a *report about* that evidence and must be derived the same
way, which is what these tests require.

The contract is moved by patching ``CompetenceContract.load``, so the whole
production composition — both repositories, the service, and the HTTP routes —
runs under the moved semantics exactly as it would after a real curriculum edit.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nornyx_lab.academy.app import create_app
from nornyx_lab.academy.competence import CompetenceContract, EvidenceFamily, FamilyRule
from nornyx_lab.academy.feedback import FeedbackConfiguration
from nornyx_lab.academy.progress import SQLiteLearnerRecordRepository
from nornyx_lab.academy.schemas import DestinationVisibility, ModuleStatus

FEEDBACK = {
    "clarity": 4,
    "confidence": 4,
    "difficulty": "right_level",
    "self_assessment": "understood",
    "comment": "clear",
}

REVISION_A = "assessment.rev-a"
REVISION_B = "assessment.rev-b"


def contract(revision: str, compatible: tuple[str, ...] = ()) -> CompetenceContract:
    return CompetenceContract(
        {
            "assessment": FamilyRule(revision, compatible),
            "capstone": FamilyRule("capstone.rev-a"),
        }
    )


@pytest.fixture
def under(monkeypatch):
    """Open the real application with a chosen competence contract in force."""

    def _open(path: Path, active: CompetenceContract) -> TestClient:
        monkeypatch.setattr(
            CompetenceContract, "load", classmethod(lambda cls: active), raising=True
        )
        return TestClient(
            create_app(
                database_path=path / "academy.db",
                frontend_dist=path / "no-frontend-build",
                feedback_configuration=FeedbackConfiguration(
                    endpoint=None, destination_visibility=DestinationVisibility.UNKNOWN
                ),
            )
        )

    return _open


def _pass_the_assessment(client: TestClient, module_id: str = "F0") -> None:
    assert client.post(f"/api/v1/modules/{module_id}/run").status_code == 200
    definition = client.app.state.assessments.definition(f"assessment.{module_id}")
    submitted = client.post(
        f"/api/v1/assessments/assessment.{module_id}/submit",
        json={"answers": list(definition.correct)},
    )
    assert submitted.status_code == 200 and submitted.json()["passed"] is True


def _module_context(client: TestClient) -> dict:
    status = client.get("/api/v1/feedback").json()
    return status["module_feedback"][0]["academy_context"]


# --------------------------------------------------------------------- attack
def test_a_pass_under_a_superseded_revision_is_never_reported_as_current_evidence(
    tmp_path, under
) -> None:
    """The exact attack.

    Pass under revision A. The curriculum moves to an incompatible revision B.
    The learner does not re-demonstrate. They then give feedback. The record
    must not carry that old pass as an assessment result — because under B it
    is not one.
    """

    with under(tmp_path, contract(REVISION_A)) as client:
        _pass_the_assessment(client)
        earned = _module_context_after_feedback(client)
        assert earned["assessment_passed"] is True
        assert earned["assessment_evidence_revision"] == REVISION_A

    # The curriculum edit. B does not declare A compatible.
    with under(tmp_path, contract(REVISION_B)) as client:
        client.delete("/api/v1/feedback")
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        context = _module_context(client)

    assert context["assessment_passed"] is None, (
        "a pass earned under superseded semantics was republished as a current pass"
    )
    assert context["assessment_score"] is None
    assert context["assessment_attempts"] == 0
    assert context["assessment_evidence_revision"] is None
    # And the record still says what the contract means *today*, so a reader can
    # see that the absence is expiry rather than a learner who never tried.
    assert context["competence_revision"] == REVISION_B


def _module_context_after_feedback(client: TestClient) -> dict:
    client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
    return _module_context(client)


def test_the_attack_does_not_rewrite_the_learner_s_history(tmp_path, under) -> None:
    """Expiry is about admissibility, never about deleting what happened."""

    with under(tmp_path, contract(REVISION_A)) as client:
        _pass_the_assessment(client)

    with sqlite3.connect(tmp_path / "academy.db") as connection:
        before = connection.execute(
            "SELECT id, score, passed, competence_revision FROM assessment_attempts"
        ).fetchall()

    with under(tmp_path, contract(REVISION_B)) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)

    with sqlite3.connect(tmp_path / "academy.db") as connection:
        after = connection.execute(
            "SELECT id, score, passed, competence_revision FROM assessment_attempts"
        ).fetchall()

    assert after == before
    assert before and before[0][3] == REVISION_A


def test_a_compatible_prior_revision_stays_usable_and_names_what_it_was_earned_under(
    tmp_path, under
) -> None:
    """The other half. Expiry must not become "everything old is worthless"."""

    with under(tmp_path, contract(REVISION_A)) as client:
        _pass_the_assessment(client)

    # B supersedes A but explicitly declares it compatible.
    with under(tmp_path, contract(REVISION_B, compatible=(REVISION_A,))) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        context = _module_context(client)

    assert context["assessment_passed"] is True
    assert context["assessment_score"] == 1.0
    assert context["assessment_attempts"] == 1
    # The two revisions are different facts and both are reported: what the
    # assessment means now, and what this evidence was actually earned under.
    assert context["competence_revision"] == REVISION_B
    assert context["assessment_evidence_revision"] == REVISION_A


def test_unbound_legacy_evidence_is_not_resurrected(tmp_path, under) -> None:
    """A row with no revision at all was earned under semantics nobody recorded."""

    with under(tmp_path, contract(REVISION_A)) as client:
        _pass_the_assessment(client)
    with sqlite3.connect(tmp_path / "academy.db") as connection:
        connection.execute("UPDATE assessment_attempts SET competence_revision = NULL")

    with under(tmp_path, contract(REVISION_A)) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        context = _module_context(client)

    assert context["assessment_passed"] is None
    assert context["assessment_score"] is None
    assert context["assessment_evidence_revision"] is None


def test_a_failure_under_current_semantics_is_false_not_unknown(tmp_path, under) -> None:
    """The distinction the null is carrying.

    ``None`` means "nothing admissible to judge". ``False`` means "judged under
    semantics that still apply, and did not pass". Collapsing them would make
    the research data unreadable.
    """

    with under(tmp_path, contract(REVISION_A)) as client:
        client.post("/api/v1/modules/F0/run")
        client.post("/api/v1/assessments/assessment.F0/submit", json={"answers": ["wrong"]})
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        context = _module_context(client)

    assert context["assessment_passed"] is False
    assert context["assessment_score"] == 0.0
    assert context["assessment_attempts"] == 1
    assert context["assessment_evidence_revision"] == REVISION_A


def test_module_status_is_content_completion_and_deliberately_does_not_expire(
    tmp_path, under
) -> None:
    """Two different claims, kept apart exactly as the dashboard keeps them.

    Completion is activity evidence and does not expire. The competence claim
    does. A reader seeing ``complete`` with no admissible assessment evidence is
    seeing the truth: the learner did the work, under rules that have since
    changed.
    """

    with under(tmp_path, contract(REVISION_A)) as client:
        _pass_the_assessment(client)

    with under(tmp_path, contract(REVISION_B)) as client:
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        context = _module_context(client)

    assert context["module_status"] == "complete"
    assert context["assessment_passed"] is None


def test_the_outbound_payload_carries_both_revisions(tmp_path, under) -> None:
    with under(tmp_path, contract(REVISION_B, compatible=(REVISION_A,))) as client:
        _pass_the_assessment(client)
        client.post("/api/v1/feedback/modules/F0", json=FEEDBACK)
        payload = client.app.state.feedback.build_payload(
            client.get("/api/v1/feedback").json()["session_id"]
        )

    context = payload["module_feedback"][0]["academy_context"]
    assert set(context) == {
        "module_status",
        "assessment_score",
        "assessment_passed",
        "assessment_attempts",
        "competence_revision",
        "assessment_evidence_revision",
        "learning_path_id",
        "session_elapsed_seconds",
    }
    assert context["competence_revision"] == REVISION_B
    assert context["assessment_evidence_revision"] == REVISION_B


def test_course_attempt_totals_count_only_admissible_evidence(tmp_path, under) -> None:
    with under(tmp_path, contract(REVISION_A)) as client:
        _pass_the_assessment(client, "F0")
        _pass_the_assessment(client, "F1")
        client.post(
            "/api/v1/feedback/course",
            json={
                "overall_clarity": 4,
                "progression": 4,
                "usefulness": 4,
                "final_confidence": 4,
                "overall_difficulty": "right_level",
                "recommend": "yes",
            },
        )
        admissible = client.get("/api/v1/feedback").json()["course_feedback"]["academy_context"]
    assert admissible["total_assessment_attempts"] == 2

    with under(tmp_path, contract(REVISION_B)) as client:
        client.post(
            "/api/v1/feedback/course",
            json={
                "overall_clarity": 4,
                "progression": 4,
                "usefulness": 4,
                "final_confidence": 4,
                "overall_difficulty": "right_level",
                "recommend": "yes",
            },
        )
        expired = client.get("/api/v1/feedback").json()["course_feedback"]["academy_context"]

    assert expired["total_assessment_attempts"] == 0, (
        "the course total counted attempts the contract no longer admits"
    )


# ------------------------------------------------------- learner-record level
def test_the_accessor_reports_unknown_rather_than_the_stale_aggregate(tmp_path) -> None:
    """Directly against the repository, so the derivation itself is pinned."""

    database = tmp_path / "academy.db"
    earned = SQLiteLearnerRecordRepository(database, competence=contract(REVISION_A))
    earned.record_execution("F0", passed=True)
    from nornyx_lab.academy.schemas import AssessmentResult

    earned.record_assessment(
        AssessmentResult(
            assessment_id="assessment.F0",
            module_id="F0",
            score=1.0,
            passed=True,
            correct_answers=("a",),
            explanation="",
            feedback=(),
            concepts_mastered=("evidence",),
        ),
        answers=("a",),
    )

    # The stale aggregate still says the learner passed — that is exactly the
    # value the old implementation reported.
    with sqlite3.connect(database) as connection:
        aggregate = connection.execute(
            "SELECT best_score, assessment_passed FROM module_progress WHERE module_id = 'F0'"
        ).fetchone()
    assert aggregate == (1.0, 1)

    moved = SQLiteLearnerRecordRepository(database, competence=contract(REVISION_B))
    outcome = moved.assessment_outcome("F0")

    assert outcome.passed is None
    assert outcome.best_score is None
    assert outcome.attempts == 0
    assert outcome.evidence_revision is None
    assert outcome.status is ModuleStatus.COMPLETE


def test_the_governing_attempt_is_the_best_admissible_pass(tmp_path) -> None:
    """Which attempt's revision gets reported, when several are admissible."""

    from nornyx_lab.academy.schemas import AssessmentResult

    database = tmp_path / "academy.db"
    active = contract(REVISION_B, compatible=(REVISION_A,))
    old = SQLiteLearnerRecordRepository(database, competence=contract(REVISION_A))
    new = SQLiteLearnerRecordRepository(database, competence=active)

    def attempt(repository, score: float, passed: bool) -> None:
        repository.record_assessment(
            AssessmentResult(
                assessment_id="assessment.F0",
                module_id="F0",
                score=score,
                passed=passed,
                correct_answers=("a",),
                explanation="",
                feedback=(),
            ),
            answers=("a",),
        )

    attempt(old, 0.4, False)  # compatible prior, failed
    attempt(old, 1.0, True)  # compatible prior, passed — the governing one
    attempt(new, 0.5, False)  # current revision, failed

    outcome = SQLiteLearnerRecordRepository(database, competence=active).assessment_outcome("F0")
    assert outcome.attempts == 3
    assert outcome.best_score == 1.0
    assert outcome.passed is True
    assert outcome.evidence_revision == REVISION_A


def test_the_current_contract_revision_is_read_from_the_contract_not_the_evidence(
    tmp_path,
) -> None:
    active = contract(REVISION_B, compatible=(REVISION_A,))
    assert active.revision(EvidenceFamily.ASSESSMENT) == REVISION_B
    repository = SQLiteLearnerRecordRepository(tmp_path / "a.db", competence=active)
    assert repository.assessment_outcome("F0").evidence_revision is None
