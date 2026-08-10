"""Drift gate for the competence contract.

The contract declares what each family's current revision stands for. These
tests recompute that from the authored inputs and fail when the two disagree —
the same declare/lock/verify discipline the curriculum teaches, applied to the
academy's own competence semantics.

If one of these fails, the fix is a decision, not a digest edit: either the
semantic change was unintended and should be reverted, or it was intended and
the family needs a new revision (plus an explicit `compatible_with` entry if
prior evidence should survive). Pasting the new digest over the old one while
keeping the revision silently invalidates nothing and re-creates exactly the
defect this contract exists to prevent.
"""

from __future__ import annotations

from nornyx_lab.academy.assessments import AssessmentService
from nornyx_lab.academy.capstone import (
    _DECLARED_IDENTITIES,
    _DECLARED_ZONES,
    _SCENARIOS,
    _SECTION_REQUIRED_FIELDS,
)
from nornyx_lab.academy.competence import (
    CompetenceContract,
    EvidenceFamily,
    compute_assessment_digest,
    compute_capstone_digest,
)


def _assessment_digest() -> str:
    service = AssessmentService()
    return compute_assessment_digest(
        service.definition(assessment_id) for assessment_id in service.ids()
    )


def _capstone_digest() -> str:
    return compute_capstone_digest(
        _SCENARIOS.values(),
        declared_identities=_DECLARED_IDENTITIES,
        declared_zones=_DECLARED_ZONES,
        required_sections=_SECTION_REQUIRED_FIELDS,
    )


def test_declared_assessment_digest_matches_the_authored_assessments() -> None:
    contract = CompetenceContract.load()
    assert contract.declared_digest(EvidenceFamily.ASSESSMENT) == _assessment_digest(), (
        "assessment semantics changed without a competence-revision decision: bump "
        "families.assessment.revision (and list the prior revision in compatible_with "
        "only if existing evidence genuinely still holds)"
    )


def test_declared_capstone_digest_matches_the_authored_capstone_semantics() -> None:
    contract = CompetenceContract.load()
    assert contract.declared_digest(EvidenceFamily.CAPSTONE) == _capstone_digest(), (
        "capstone competence semantics changed without a competence-revision decision: "
        "bump families.capstone.revision (and list the prior revision in compatible_with "
        "only if existing evidence genuinely still holds)"
    )


def test_digest_tracks_the_fields_that_decide_what_evidence_means() -> None:
    """A change to a tested concept or accepted answer must move the digest."""

    service = AssessmentService()
    definitions = [service.definition(assessment_id) for assessment_id in service.ids()]
    baseline = compute_assessment_digest(definitions)

    retested = definitions[0].model_copy(update={"concepts": ("something-else",)})
    assert compute_assessment_digest([retested, *definitions[1:]]) != baseline

    reanswered = definitions[0].model_copy(update={"correct": ("different-option",)})
    assert compute_assessment_digest([reanswered, *definitions[1:]]) != baseline

    rethresholded = definitions[0].model_copy(update={"minimum_score": 0.5})
    assert compute_assessment_digest([rethresholded, *definitions[1:]]) != baseline


def test_digest_tracks_the_learner_visible_stimulus() -> None:
    """The stimulus decides what an answer id *means*, so it is semantic.

    ``correct`` stores option ids. Negating a prompt, or relabelling the option
    that id points at, inverts what the learner had to demonstrate while every
    id stays identical. An earlier version of this gate excluded the stimulus
    and would have let exactly that change pass without a revision — the defect
    the competence contract exists to prevent.
    """

    service = AssessmentService()
    definitions = [service.definition(assessment_id) for assessment_id in service.ids()]
    baseline = compute_assessment_digest(definitions)

    negated = definitions[0].model_copy(
        update={"prompt": "Which action does NOT require approval?"}
    )
    assert compute_assessment_digest([negated, *definitions[1:]]) != baseline

    recontextualised = definitions[0].model_copy(
        update={"context": "A materially different situation to reason about."}
    )
    assert compute_assessment_digest([recontextualised, *definitions[1:]]) != baseline

    first_option = definitions[0].options[0]
    inverted_label = definitions[0].model_copy(
        update={
            "options": (
                first_option.model_copy(update={"label": "Allow without human approval"}),
                *definitions[0].options[1:],
            )
        }
    )
    assert compute_assessment_digest([inverted_label, *definitions[1:]]) != baseline


def test_digest_ignores_material_shown_only_after_scoring() -> None:
    """Explanations cannot change what the learner had to demonstrate."""

    service = AssessmentService()
    definitions = [service.definition(assessment_id) for assessment_id in service.ids()]
    baseline = compute_assessment_digest(definitions)

    reworded = definitions[0].model_copy(
        update={
            "explanation": "A clearer explanation of exactly the same answer.",
            "incorrect_explanations": {"zzz": "A clearer note about a wrong choice."},
        }
    )
    assert compute_assessment_digest([reworded, *definitions[1:]]) == baseline


def test_digest_ignores_option_order_and_definition_order() -> None:
    """Serialisation changes are not semantic and must not raise false drift."""

    service = AssessmentService()
    definitions = [service.definition(assessment_id) for assessment_id in service.ids()]
    baseline = compute_assessment_digest(definitions)

    multi_option = next(item for item in definitions if len(item.options) > 1)
    reordered_options = multi_option.model_copy(
        update={"options": tuple(reversed(multi_option.options))}
    )
    swapped = [reordered_options if item.id == multi_option.id else item for item in definitions]
    assert compute_assessment_digest(swapped) == baseline

    assert compute_assessment_digest(list(reversed(definitions))) == baseline


def test_capstone_digest_tracks_scenario_and_authorship_semantics() -> None:
    baseline = _capstone_digest()

    narrowed = compute_capstone_digest(
        _SCENARIOS.values(),
        declared_identities=_DECLARED_IDENTITIES,
        declared_zones=_DECLARED_ZONES,
        # Dropping an authorship requirement changes what an eligible run proves.
        required_sections={
            key: [field for field in value if field != "approval_mode"]
            for key, value in _SECTION_REQUIRED_FIELDS.items()
        },
    )
    assert narrowed != baseline

    fewer_identities = compute_capstone_digest(
        _SCENARIOS.values(),
        declared_identities=sorted(_DECLARED_IDENTITIES)[:2],
        declared_zones=_DECLARED_ZONES,
        required_sections=_SECTION_REQUIRED_FIELDS,
    )
    assert fewer_identities != baseline
