"""Data-driven learner assessments; repository regressions are not assessments."""

from __future__ import annotations

import json
from importlib.resources import files

from .schemas import (
    AssessmentDefinition,
    AssessmentKind,
    AssessmentResult,
    AssessmentSubmission,
    PublicAssessment,
)


class AssessmentService:
    def __init__(self) -> None:
        raw = json.loads(
            files("nornyx_lab.academy.content")
            .joinpath("assessments.json")
            .read_text(encoding="utf-8")
        )
        definitions = tuple(AssessmentDefinition.model_validate(item) for item in raw)
        self._by_id = {item.id: item for item in definitions}
        if len(self._by_id) != len(definitions):
            raise ValueError("assessment ids must be unique")

    def ids(self) -> tuple[str, ...]:
        return tuple(self._by_id)

    def definition(self, assessment_id: str) -> AssessmentDefinition:
        try:
            return self._by_id[assessment_id]
        except KeyError as exc:
            raise KeyError(f"unknown assessment {assessment_id!r}") from exc

    def public(self, assessment_id: str) -> PublicAssessment:
        definition = self.definition(assessment_id)
        return PublicAssessment.model_validate(
            definition.model_dump(exclude={"correct", "explanation", "incorrect_explanations"})
        )

    def submit(
        self, assessment_id: str, submission: AssessmentSubmission, *, concepts: tuple[str, ...]
    ) -> AssessmentResult:
        definition = self.definition(assessment_id)
        supplied = submission.answers
        if definition.kind == AssessmentKind.ORDERING:
            correct_count = sum(
                actual == expected
                for actual, expected in zip(supplied, definition.correct, strict=False)
            )
            denominator = max(len(definition.correct), len(supplied), 1)
            score = correct_count / denominator
            passed = supplied == definition.correct and score >= definition.minimum_score
        else:
            expected_set = set(definition.correct)
            supplied_set = set(supplied)
            true_positive = len(expected_set & supplied_set)
            false_positive = len(supplied_set - expected_set)
            denominator = max(len(expected_set), 1)
            score = max(0.0, (true_positive - false_positive) / denominator)
            passed = supplied_set == expected_set and score >= definition.minimum_score

        feedback: list[str] = []
        if passed:
            feedback.append(definition.explanation)
        else:
            for answer in supplied:
                explanation = definition.incorrect_explanations.get(answer)
                if explanation:
                    feedback.append(explanation)
            if not feedback:
                feedback.append("Revisit the evidence and enforcement boundary, then try again.")
            feedback.append(definition.explanation)

        return AssessmentResult(
            assessment_id=definition.id,
            module_id=definition.module_id,
            score=round(score, 4),
            passed=passed,
            correct_answers=definition.correct,
            explanation=definition.explanation,
            feedback=tuple(feedback),
            concepts_mastered=concepts if passed else (),
            concepts_needing_review=() if passed else concepts,
        )
