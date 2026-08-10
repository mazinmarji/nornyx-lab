from __future__ import annotations

import pytest

from nornyx_lab.academy.assessments import AssessmentService
from nornyx_lab.academy.catalog import CurriculumRepository
from nornyx_lab.academy.schemas import AssessmentKind, AssessmentSubmission


def test_every_curriculum_module_has_a_meaningful_assessment() -> None:
    service = AssessmentService()
    modules = CurriculumRepository().modules()

    assert len(service.ids()) == len(modules) == 31
    for module in modules:
        definition = service.definition(module.completion.assessment_id)
        assert definition.module_id == module.id
        assert len(definition.options) >= 2
        assert definition.correct
        assert definition.prompt.endswith(("?", "."))


def test_public_assessment_never_exposes_answer_or_explanation() -> None:
    service = AssessmentService()
    public = service.public("assessment.F0")

    payload = public.model_dump(mode="json")
    assert "correct" not in payload
    assert "correct_answers" not in payload
    assert "explanation" not in payload


def test_correct_answer_passes_and_masters_only_declared_concepts() -> None:
    # The caller no longer supplies the module's whole concept list; the
    # previous assertion (all supplied concepts returned as mastered) was the
    # measurement defect the mastery model removes.
    service = AssessmentService()
    definition = service.definition("assessment.F3")

    result = service.submit(definition.id, AssessmentSubmission(answers=definition.correct))

    assert result.passed is True
    assert result.score == 1.0
    assert result.concepts_mastered == definition.concepts
    assert result.concepts_needing_review == ()


def test_wrong_extra_answer_is_penalized_and_returns_review_concepts() -> None:
    service = AssessmentService()
    definition = next(
        item
        for item in (service.definition(assessment_id) for assessment_id in service.ids())
        if item.kind is not AssessmentKind.ORDERING
        and any(option.id not in item.correct for option in item.options)
    )
    wrong = next(option.id for option in definition.options if option.id not in definition.correct)

    result = service.submit(
        definition.id,
        AssessmentSubmission(answers=(*definition.correct, wrong)),
    )

    assert result.passed is False
    assert result.score < 1.0
    assert result.concepts_mastered == ()
    assert result.concepts_needing_review == definition.concepts


def test_ordering_requires_exact_order() -> None:
    service = AssessmentService()
    definition = next(
        service.definition(assessment_id)
        for assessment_id in service.ids()
        if service.definition(assessment_id).kind is AssessmentKind.ORDERING
    )

    result = service.submit(
        definition.id,
        AssessmentSubmission(answers=tuple(reversed(definition.correct))),
    )

    assert result.passed is False
    assert result.score < 1.0


def test_unknown_assessment_fails_loudly() -> None:
    with pytest.raises(KeyError, match="unknown assessment"):
        AssessmentService().definition("assessment.missing")
