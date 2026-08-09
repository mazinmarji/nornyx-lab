"""Evidence-based concept mastery.

The defect these tests pin down: one passed module assessment used to return
every concept attached to the module as ``concepts_mastered``. Mastery must
instead be granted only for the concepts an assessment actually tests, and a
stored record must never fabricate mastery it cannot substantiate.
"""

from __future__ import annotations

import json
import sqlite3

from fastapi.testclient import TestClient

from nornyx_lab.academy.app import create_app
from nornyx_lab.academy.assessments import AssessmentService
from nornyx_lab.academy.catalog import CurriculumRepository
from nornyx_lab.academy.progress import SQLiteLearnerRecordRepository
from nornyx_lab.academy.schemas import AssessmentResult, AssessmentSubmission, ModuleStatus


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(database_path=tmp_path / "mastery.db", frontend_dist=tmp_path))


# --------------------------------------------------------------- declarations


def test_every_assessment_declares_a_proper_subset_of_module_concepts() -> None:
    """Each assessment names what it tests, and never the whole module.

    Every module in this curriculum teaches several concepts. If an assessment
    declared them all, a single correct answer would go back to substantiating
    blanket mastery, which is exactly the defect being removed.
    """

    service = AssessmentService()
    modules = {module.id: module for module in CurriculumRepository().modules()}

    for assessment_id in service.ids():
        definition = service.definition(assessment_id)
        module = modules[definition.module_id]
        declared = set(definition.concepts)
        assert declared, f"{assessment_id} declares no tested concepts"
        assert declared <= set(module.concepts), (
            f"{assessment_id} declares concepts the module does not teach: "
            f"{sorted(declared - set(module.concepts))}"
        )
        assert declared < set(module.concepts), (
            f"{assessment_id} claims to test every concept of module {module.id}; "
            "one item cannot substantiate a whole module"
        )


def test_public_assessment_exposes_tested_concepts_but_not_answers() -> None:
    public = AssessmentService().public("assessment.F0")
    payload = public.model_dump(mode="json")
    assert payload["concepts"], "the learner should see which concepts an item tests"
    assert "correct" not in payload
    assert "explanation" not in payload


# ------------------------------------------------------------------ granting


def test_passing_grants_only_the_declared_concepts() -> None:
    """Module teaches A, B, C…; the assessment tests only its declared subset.

    Passing masters the declared subset and nothing else.
    """

    service = AssessmentService()
    modules = {module.id: module for module in CurriculumRepository().modules()}
    definition = service.definition("assessment.F0")
    module = modules[definition.module_id]
    untested = set(module.concepts) - set(definition.concepts)
    assert untested, "F0 must have concepts its assessment does not test"

    result = service.submit(definition.id, AssessmentSubmission(answers=definition.correct))

    assert result.passed is True
    assert set(result.concepts_mastered) == set(definition.concepts)
    assert not set(result.concepts_mastered) & untested


def test_failing_marks_only_the_tested_concepts_for_review() -> None:
    service = AssessmentService()
    definition = service.definition("assessment.F0")
    wrong = next(option.id for option in definition.options if option.id not in definition.correct)

    result = service.submit(definition.id, AssessmentSubmission(answers=(wrong,)))

    assert result.passed is False
    assert result.concepts_mastered == ()
    assert set(result.concepts_needing_review) == set(definition.concepts)


# ------------------------------------------------------- end-to-end via API


def test_api_pass_yields_partial_mastery_not_blanket_mastery(tmp_path) -> None:
    client = _client(tmp_path)
    definition = AssessmentService().definition("assessment.F0")
    module = next(
        item for item in CurriculumRepository().modules() if item.id == definition.module_id
    )

    response = client.post(
        "/api/v1/assessments/assessment.F0/submit",
        json={"answers": list(definition.correct)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert set(body["concepts_mastered"]) == set(definition.concepts)

    progress = client.get("/api/v1/progress").json()
    record = next(item for item in progress["modules"] if item["module_id"] == "F0")
    assert set(record["concepts_mastered"]) == set(definition.concepts)
    pending = set(module.concepts) - set(definition.concepts)
    assert set(record["concepts_pending_evidence"]) == pending
    assert pending, "the distinction only means something if something stays pending"
    assert set(progress["concepts_mastered"]) == set(definition.concepts)
    assert pending <= set(progress["concepts_pending_evidence"])


def test_repeated_passes_do_not_duplicate_or_grow_evidence(tmp_path) -> None:
    client = _client(tmp_path)
    definition = AssessmentService().definition("assessment.F0")

    for _ in range(3):
        response = client.post(
            "/api/v1/assessments/assessment.F0/submit",
            json={"answers": list(definition.correct)},
        )
        assert response.status_code == 200

    progress = client.get("/api/v1/progress").json()
    record = next(item for item in progress["modules"] if item["module_id"] == "F0")
    assert sorted(record["concepts_mastered"]) == sorted(set(definition.concepts))
    assert len(record["concepts_mastered"]) == len(set(definition.concepts))
    assert record["assessment_attempts"] == 3


def test_concept_evidence_transfers_across_modules_that_teach_it(tmp_path) -> None:
    """A concept evidenced in one module counts wherever it is taught.

    Mastering every concept of a multi-concept module therefore requires more
    than one independent learner action, in whichever modules test them.
    """

    client = _client(tmp_path)
    service = AssessmentService()
    modules = {module.id: module for module in CurriculumRepository().modules()}

    shared = None
    for assessment_id in service.ids():
        definition = service.definition(assessment_id)
        for concept in definition.concepts:
            for other in modules.values():
                if other.id != definition.module_id and concept in other.concepts:
                    shared = (definition, concept, other)
                    break
            if shared:
                break
        if shared:
            break
    assert shared, "no concept is taught by two modules; the transfer rule is untestable"
    definition, concept, other_module = shared

    response = client.post(
        f"/api/v1/assessments/{definition.id}/submit",
        json={"answers": list(definition.correct)},
    )
    assert response.status_code == 200

    progress = client.get("/api/v1/progress").json()
    other = next(item for item in progress["modules"] if item["module_id"] == other_module.id)
    assert concept in other["concepts_mastered"]


# ----------------------------------------------------------------- migration


def test_legacy_record_degrades_to_completed_without_fabricated_mastery(tmp_path) -> None:
    """A pre-remediation store granted every module concept on one pass.

    Reading it under the new model keeps completion but derives mastery only
    from what the recorded attempts can substantiate under the current
    declarations: completed, but mastery not yet demonstrated.
    """

    db_path = tmp_path / "legacy.db"
    service = AssessmentService()
    catalog = CurriculumRepository()
    module = next(item for item in catalog.modules() if item.id == "F0")
    definition = service.definition("assessment.F0")

    # Write the legacy shape directly: an inflated module_progress row plus one
    # passed attempt, exactly what the old code produced.
    legacy = SQLiteLearnerRecordRepository(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO module_progress (
                learner_id, module_id, executions, execution_passed,
                assessment_attempts, assessment_passed, best_score,
                concepts_mastered, concepts_needing_review, last_activity
            ) VALUES ('local', 'F0', 1, 1, 1, 1, 1.0, ?, '[]', '2026-01-01T00:00:00Z')
            """,
            (json.dumps(sorted(module.concepts)),),
        )
        connection.execute(
            """
            INSERT INTO assessment_attempts (
                learner_id, assessment_id, module_id, answers, score, passed,
                feedback, version_binding, created_at
            ) VALUES ('local', 'assessment.F0', 'F0', '[]', 1.0, 1, '[]', '{}',
                      '2026-01-01T00:00:00Z')
            """
        )
    del legacy

    repository = SQLiteLearnerRecordRepository(
        db_path,
        assessment_concepts={
            assessment_id: service.definition(assessment_id).concepts
            for assessment_id in service.ids()
        },
        module_concepts={item.id: item.concepts for item in catalog.modules()},
    )
    progress = repository.get("F0")

    assert progress.status is ModuleStatus.COMPLETE
    assert set(progress.concepts_mastered) == set(definition.concepts)
    assert set(progress.concepts_pending_evidence) == set(module.concepts) - set(
        definition.concepts
    )


def test_unknown_legacy_assessment_grants_nothing(tmp_path) -> None:
    """An attempt whose assessment no longer exists must not invent mastery."""

    db_path = tmp_path / "legacy.db"
    SQLiteLearnerRecordRepository(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO assessment_attempts (
                learner_id, assessment_id, module_id, answers, score, passed,
                feedback, version_binding, created_at
            ) VALUES ('local', 'assessment.retired', 'F0', '[]', 1.0, 1, '[]', '{}',
                      '2026-01-01T00:00:00Z')
            """
        )

    repository = SQLiteLearnerRecordRepository(
        db_path,
        assessment_concepts={},
        module_concepts={"F0": ("assistant", "agent")},
    )
    progress = repository.get("F0")
    assert progress.concepts_mastered == ()
    assert set(progress.concepts_pending_evidence) == {"agent", "assistant"}


def _result(*, passed: bool, concepts: tuple[str, ...]) -> AssessmentResult:
    return AssessmentResult(
        assessment_id="assessment.F0",
        module_id="F0",
        score=1.0 if passed else 0.0,
        passed=passed,
        correct_answers=("bounded",),
        explanation="Only the named cooperative surface is in scope.",
        feedback=("Keep the claim bounded.",),
        concepts_mastered=concepts if passed else (),
        concepts_needing_review=() if passed else concepts,
    )


def test_repository_stores_granted_concepts_per_attempt(tmp_path) -> None:
    repository = SQLiteLearnerRecordRepository(tmp_path / "progress.db")
    repository.record_assessment(
        _result(passed=True, concepts=("assurance boundary",)), answers=("bounded",)
    )
    progress = repository.get("F0")
    assert progress.concepts_mastered == ("assurance boundary",)
