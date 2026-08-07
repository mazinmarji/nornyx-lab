from __future__ import annotations

from nornyx_lab.academy.progress import SQLiteLearnerRecordRepository
from nornyx_lab.academy.schemas import AssessmentResult, ModuleStatus


def _result(*, passed: bool, score: float) -> AssessmentResult:
    return AssessmentResult(
        assessment_id="assessment.F0",
        module_id="F0",
        score=score,
        passed=passed,
        correct_answers=("bounded",),
        explanation="Only the named cooperative surface is in scope.",
        feedback=("Keep the claim bounded.",),
        concepts_mastered=("assurance boundary",) if passed else (),
        concepts_needing_review=() if passed else ("assurance boundary",),
    )


def test_completion_requires_both_execution_and_assessment(tmp_path) -> None:
    repository = SQLiteLearnerRecordRepository(
        tmp_path / "progress.db", clock=lambda: "2026-08-07T00:00:00Z"
    )

    assert repository.get("F0").status is ModuleStatus.NOT_STARTED
    assert repository.record_execution("F0", passed=True).status is ModuleStatus.IN_PROGRESS
    progress = repository.record_assessment(_result(passed=True, score=1.0), answers=("bounded",))

    assert progress.status is ModuleStatus.COMPLETE
    assert progress.executions == 1
    assert progress.assessment_attempts == 1
    assert progress.concepts_mastered == ("assurance boundary",)


def test_failed_assessment_marks_review_but_later_pass_preserves_best_score(tmp_path) -> None:
    repository = SQLiteLearnerRecordRepository(tmp_path / "progress.db")
    repository.record_execution("F0", passed=True)

    failed = repository.record_assessment(_result(passed=False, score=0.0), answers=("broad",))
    passed = repository.record_assessment(_result(passed=True, score=1.0), answers=("bounded",))

    assert failed.status is ModuleStatus.NEEDS_REVIEW
    assert failed.concepts_needing_review == ("assurance boundary",)
    assert passed.status is ModuleStatus.COMPLETE
    assert passed.best_score == 1.0
    assert passed.assessment_attempts == 2
    assert passed.concepts_needing_review == ()


def test_dashboard_export_and_reset_are_local_and_explicit(tmp_path) -> None:
    repository = SQLiteLearnerRecordRepository(
        tmp_path / "progress.db", clock=lambda: "2026-08-07T00:00:00Z"
    )
    repository.record_execution("F0", passed=True, version_binding={"academy": "2.0.0"})
    repository.record_assessment(
        _result(passed=True, score=1.0),
        answers=("bounded",),
        version_binding={"academy": "2.0.0"},
    )

    dashboard = repository.dashboard(("F0", "24"))
    exported = repository.export(("F0", "24"))

    assert dashboard.completed_modules == 1
    assert dashboard.total_modules == 2
    assert dashboard.completion_percent == 50.0
    assert dashboard.capstone_status is ModuleStatus.NOT_STARTED
    assert exported.schema_id == "nornyx.academy.progress.v1"
    assert exported.assessment_history[0]["version_binding"] == {"academy": "2.0.0"}
    assert "not an identity credential" in exported.assurance_note

    repository.reset()
    assert repository.dashboard(("F0", "24")).completed_modules == 0
