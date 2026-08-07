"""Structural invariants of the teaching layer.

These tests do not judge whether the writing is good — that is not automatable
and pretending otherwise would produce tests that fail on a synonym. They check
the *structure* the pedagogy depends on: that every module has a scaffold, that
the plain-language layer exists wherever a formal term does, and above all that
the derived explanation never narrates something the run did not report.

The last group is the important one. `explain.py` is the only place the academy
makes a claim about behaviour, so it is the only place the academy could commit
the overclaim it spends thirty-one modules teaching against.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from nornyx_lab.academy.catalog import CurriculumRepository
from nornyx_lab.academy.explain import explain_run
from nornyx_lab.academy.pedagogy import PedagogyRepository
from nornyx_lab.academy.scenarios import run_atlas_demo
from nornyx_lab.academy.schemas import CounterMeaning, DemoOptions, ModuleStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"


@pytest.fixture(scope="module")
def pedagogy() -> PedagogyRepository:
    return PedagogyRepository()


@pytest.fixture(scope="module")
def module_ids() -> tuple[str, ...]:
    return tuple(module.id for module in CurriculumRepository().modules())


# --------------------------------------------------------------- coverage
def test_every_module_has_a_lesson_scaffold(pedagogy, module_ids):
    """A module without a scaffold silently falls back to the old dense page."""
    missing = sorted(set(module_ids) - pedagogy.authored_module_ids())
    assert not missing, f"modules with no teaching scaffold: {missing}"


def test_the_scaffold_references_no_unknown_module(pedagogy, module_ids):
    extra = sorted(pedagogy.authored_module_ids() - set(module_ids))
    assert not extra, f"teaching.json describes modules that do not exist: {extra}"


def test_every_module_appears_in_the_conceptual_curriculum(pedagogy, module_ids):
    """The stage map is the learner's structure; a module absent from it is
    unreachable except by deep link."""
    missing = sorted(set(module_ids) - pedagogy.staged_module_ids())
    assert not missing, f"modules missing from stages.json: {missing}"


def test_every_referenced_glossary_term_exists(pedagogy):
    unknown = sorted(pedagogy.referenced_term_ids() - pedagogy.known_term_ids())
    assert not unknown, f"lessons reference undefined glossary terms: {unknown}"


@pytest.mark.parametrize(
    "term_id",
    [
        "llm", "assistant", "agent", "tool", "side-effect", "prompt", "context",
        "prompt-injection", "identity", "capability", "authority", "policy",
        "decision", "enforcement", "trust-zone", "approval", "evidence",
        "assurance", "lock", "drift", "occurrence", "retry", "handoff",
        "adapter", "conformance",
    ],
)
def test_the_required_vocabulary_is_defined(pedagogy, term_id):
    assert term_id in pedagogy.known_term_ids(), f"glossary is missing {term_id!r}"


def test_every_glossary_term_carries_all_five_parts(pedagogy):
    """A term without a 'why' is a dictionary entry, not a teaching aid."""
    for term in pedagogy.glossary().terms:
        for field in ("plain", "why", "example", "formal", "nornyx"):
            assert getattr(term, field).strip(), f"{term.id} has an empty {field}"


# -------------------------------------------------------------- sequencing
def test_the_orientation_introduces_no_specialist_vocabulary(pedagogy):
    """The first explanation a learner reads must not assume the vocabulary the
    academy exists to teach. These terms have to arrive later, as answers to a
    problem already witnessed."""
    orientation = pedagogy.orientation()
    text = json.dumps(orientation.model_dump(mode="json")).lower()
    forbidden = [
        "pdp", "pep", "policy decision point", "policy enforcement point",
        "evidence binding", "assurance tier", "contract revision",
        "subject revision", "trust zone", "occurrence identity",
    ]
    found = [term for term in forbidden if term in text]
    assert not found, f"the orientation uses specialist terms before teaching them: {found}"


def test_every_lesson_states_one_thing_to_learn(pedagogy, module_ids):
    for module_id in module_ids:
        teaching = pedagogy.teaching(module_id)
        assert teaching.learn.strip(), f"{module_id} has no learning sentence"
        # One sentence, not a paragraph: this line has to outrank the run
        # controls visually, and it cannot do that at three sentences long.
        assert teaching.learn.count(". ") <= 1, (
            f"{module_id} learning sentence is more than one sentence: {teaching.learn!r}"
        )


def test_every_lesson_asks_before_it_tells(pedagogy, module_ids):
    """Prediction is what makes the observation land, so it must exist and must
    offer real alternatives."""
    for module_id in module_ids:
        prediction = pedagogy.teaching(module_id).prediction
        assert prediction.prompt.strip().endswith("?"), (
            f"{module_id} prediction prompt is not a question: {prediction.prompt!r}"
        )
        assert len(prediction.options) >= 2, f"{module_id} prediction has no real choice"


def test_every_lesson_names_a_concept_in_plain_language_first(pedagogy, module_ids):
    for module_id in module_ids:
        concept = pedagogy.teaching(module_id).concept
        assert concept.plain_name.strip(), f"{module_id} has no plain concept name"
        assert concept.formal_term.strip(), f"{module_id} has no formal term"
        assert concept.plain_name != concept.formal_term, (
            f"{module_id} plain name and formal term are identical, so nothing is being "
            f"translated for the learner"
        )


def test_every_lesson_bounds_the_nornyx_contribution(pedagogy, module_ids):
    """Authored teaching text describes Nornyx's responsibility in a topic. It
    must never be phrased as a claim about a specific run's outcome, because
    nothing verifies authored text."""
    outcome_claims = re.compile(
        r"\b(prevented|blocked|stopped|recorded \d|proved|0 attempts)\b", re.I
    )
    for module_id in module_ids:
        role = pedagogy.teaching(module_id).nornyx_role
        assert role.strip(), f"{module_id} does not say where Nornyx fits"
        assert not outcome_claims.search(role), (
            f"{module_id} nornyx_role asserts a run outcome in authored text: {role!r}. "
            f"Outcome claims must be derived in explain.py from an actual run."
        )


# ------------------------------------------------- the derived explanation
def test_the_explanation_is_derived_for_a_real_run():
    explanation = run_atlas_demo(DemoOptions()).explanation
    assert explanation is not None
    assert explanation.determinate
    # Every field the "teach me" layer promises.
    assert explanation.headline
    assert explanation.what_happened
    assert explanation.why
    assert explanation.nornyx_role
    assert explanation.proves
    assert explanation.does_not_prove
    assert explanation.remember


def test_the_explanation_always_states_a_limitation():
    """Guided mode may simplify the wording of a limit. It may never drop it."""
    for options in (
        DemoOptions(),
        DemoOptions(enforcement_enabled=False),
        DemoOptions(injection_enabled=False),
        DemoOptions(enforcement_failure=True, failure_mode="fail_open"),
        DemoOptions(approval_state="expired"),
    ):
        explanation = run_atlas_demo(options).explanation
        assert explanation is not None
        assert explanation.does_not_prove, f"no limitation stated for {options!r}"


def test_an_unattempted_action_is_never_reported_as_a_prevention():
    """The single most damaging thing this layer could do.

    With no injection the agent never proposes publishing, so both paths record
    0/0. Reading that as "the control prevented it" would teach a learner to
    credit a control for an attack that never happened — and 0/0 is exactly the
    pattern the curriculum spends four modules on.
    """
    run = run_atlas_demo(DemoOptions(injection_enabled=False))
    governed = next(v for v in run.variants if v.id == "governed")
    publish = next(c for c in governed.counters if c.action == "publish_external")
    assert publish.meaning is CounterMeaning.NOT_PLANNED, "fixture assumption changed"

    explanation = run.explanation
    assert explanation is not None
    assert explanation.determinate
    text = f"{explanation.headline} {explanation.what_happened} {explanation.proves}".lower()
    assert "prevent" not in text, (
        f"a run where nothing was attempted was narrated as a prevention: {text!r}"
    )
    assert "never tried" in explanation.headline.lower()


def test_an_unenforced_rule_is_reported_as_having_changed_nothing():
    """Enforcement off is the declaration-is-not-enforcement lesson, not an error."""
    explanation = run_atlas_demo(DemoOptions(enforcement_enabled=False)).explanation
    assert explanation is not None
    assert explanation.determinate, "this configuration teaches a lesson; it is not a failure"
    assert "never asked" in explanation.headline.lower()
    assert "nothing" in explanation.nornyx_role.lower()


def test_a_failed_check_that_allowed_the_action_is_reported_honestly():
    explanation = run_atlas_demo(
        DemoOptions(enforcement_failure=True, failure_mode="fail_open")
    ).explanation
    assert explanation is not None
    assert explanation.determinate
    assert "failed" in explanation.headline.lower()
    assert "continue" in explanation.headline.lower() or "ran" in explanation.headline.lower()


def test_the_explanation_names_the_evidence_producer():
    """Who wrote the record is part of what the record is worth."""
    explanation = run_atlas_demo(DemoOptions()).explanation
    assert explanation is not None
    limits = " ".join(explanation.does_not_prove)
    assert "synthetic_harness" in limits
    assert "same process" in limits


def test_an_inconsistent_response_is_refused_rather_than_narrated():
    """A counter whose numbers contradict its own stated meaning cannot support
    any reading, and the layer must say so instead of picking one."""
    run = run_atlas_demo(DemoOptions())
    governed = next(v for v in run.variants if v.id == "governed")
    broken_counter = governed.counters[-1].model_copy(
        update={"attempts": 0, "completions": 5, "meaning": CounterMeaning.EXECUTED}
    )
    broken_variant = governed.model_copy(
        update={"counters": (*governed.counters[:-1], broken_counter)}
    )
    ungoverned = next(v for v in run.variants if v.id == "ungoverned")
    broken_run = run.model_copy(update={"variants": (ungoverned, broken_variant)})

    explanation = explain_run(broken_run)
    assert not explanation.determinate
    assert "cannot be read" in explanation.headline.lower()


# ---------------------------------------------------------------- progress
def test_progress_is_expressed_as_concepts_not_only_counts(pedagogy):
    stages = pedagogy.stages({})
    assert stages.next_concepts, "a learner with no progress must still be told what is next"
    assert all(stage.total_steps > 0 for stage in stages.stages)

    complete = dict.fromkeys(
        [module_id for module_id in pedagogy.staged_module_ids()], ModuleStatus.COMPLETE
    )
    finished = pedagogy.stages(complete)
    assert finished.understood_concepts, "completed modules must yield understood concepts"
    assert sum(stage.completed_steps for stage in finished.stages) == sum(
        stage.total_steps for stage in finished.stages
    )


# ----------------------------------------------------- browser structure
def _read(*parts: str) -> str:
    return (FRONTEND_SRC.joinpath(*parts)).read_text(encoding="utf-8")


def test_guided_is_the_default_mode():
    """Nobody is dropped into professional density without choosing it."""
    source = _read("context", "ModeContext.tsx")
    assert 'useState<LearnerMode>(readStoredMode)' in source
    assert '=== "explore" ? "explore" : "guided"' in source


def test_the_mode_switch_is_always_reachable():
    """Hiding the existence of depth would be its own kind of dishonesty."""
    assert "ModeSwitch" in _read("components", "Shell.tsx")


def test_the_lesson_page_teaches_before_it_runs():
    """The order of these sections is the whole redesign."""
    full = _read("pages", "LessonPage.tsx")
    # Measure the rendered order, not the import order: imports are sorted
    # alphabetically and would otherwise decide the result.
    source = full[full.index("export function LessonPage") :]
    order = [
        "LearningSentence",       # what you will learn
        "lesson-question",        # the question
        "lesson-story",           # the situation
        "PredictionStep",         # predict
        "execution-panel",        # run
        "ConceptName",            # name the concept, after the result
        "lesson-takeaway",        # takeaway
        "AssessmentPanel",        # check understanding, last
    ]
    positions = [source.index(marker) for marker in order]
    assert positions == sorted(positions), (
        "lesson sections are out of pedagogical order: "
        f"{[m for _, m in sorted(zip(positions, order, strict=True))]}"
    )


def test_the_assessment_never_precedes_the_run():
    source = _read("pages", "LessonPage.tsx")
    assert "hasRun ? (" in source and "AssessmentPanel" in source


def test_the_demo_asks_for_a_prediction_before_the_first_run():
    story = json.loads(
        (
            REPO_ROOT / "src" / "nornyx_lab" / "academy" / "content" / "demo_story.json"
        ).read_text(encoding="utf-8")
    )
    kinds = [screen["kind"] for screen in story["screens"]]
    assert "predict" in kinds, "the demo never asks the learner to commit"
    assert kinds.index("predict") < kinds.index("run"), (
        "the demo runs before it asks for a prediction, so the result cannot violate an expectation"
    )


def test_the_demo_states_its_limits_after_the_proof():
    story = json.loads(
        (
            REPO_ROOT / "src" / "nornyx_lab" / "academy" / "content" / "demo_story.json"
        ).read_text(encoding="utf-8")
    )
    kinds = [screen["kind"] for screen in story["screens"]]
    assert kinds.index("proof") < kinds.index("limits")
    limits = next(screen for screen in story["screens"] if screen["kind"] == "limits")
    assert len(limits["not_proved"]) >= 3
    assert "Tier 2" in limits["tier"]["name"]


def test_technical_panels_explain_themselves():
    """Never assume the learner knows why a panel exists."""
    for page, expected in (
        (("pages", "LessonPage.tsx"), 2),
        (("pages", "DemoPage.tsx"), 1),
        (("components", "Teaching.tsx"), 1),
    ):
        source = _read(*page)
        assert source.count("WhatAmILookingAt") >= expected, (
            f"{page[-1]} does not explain its technical panels"
        )
