from __future__ import annotations

import pytest
from nornyx.agentic import CapabilityRequest, EvaluationContext, load_authorizer

from nornyx_lab.academy import scenarios
from nornyx_lab.academy.schemas import (
    ClaimStatus,
    CounterMeaning,
    DemoOptions,
    EvidenceStatus,
)
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import shared_contract
from nornyx_lab.model import Plan, ToolCall


def _variant(run, variant_id: str):
    return next(item for item in run.variants if item.id == variant_id)


def _counter(run, variant_id: str, action: str = "publish_external"):
    variant = _variant(run, variant_id)
    return next(item for item in variant.counters if item.action == action)


def _decision(run, variant_id: str, *, capability: str):
    return next(
        item for item in _variant(run, variant_id).decisions if item.capability == capability
    )


def test_default_demo_uses_one_plan_and_proves_the_core_ab(monkeypatch) -> None:
    calls = 0
    original = scenarios.DeterministicPlanner.plan

    def counted(self, task: str, context: str = ""):
        nonlocal calls
        calls += 1
        return original(self, task, context)

    monkeypatch.setattr(scenarios.DeterministicPlanner, "plan", counted)
    run = scenarios.run_atlas_demo()

    assert calls == 1
    assert run.deterministic is True
    assert [item.action for item in run.plan] == [
        "search_web",
        "draft_briefing",
        "publish_external",
    ]
    assert (_counter(run, "ungoverned").attempts, _counter(run, "ungoverned").completions) == (
        1,
        1,
    )
    assert (_counter(run, "governed").attempts, _counter(run, "governed").completions) == (
        0,
        0,
    )
    governed = _variant(run, "governed")
    assert _decision(run, "governed", capability="publish_external").code == "CAPABILITY_DENIED"
    crossing = _decision(run, "governed", capability="cross_zone_publication")
    assert crossing.code == "CROSSING_APPROVAL_REQUIRED"
    assert crossing.approval_state == "missing"
    assert governed.evidence.validation_status == EvidenceStatus.PASS
    assert any("cooperative" in claim.limitation.lower() for claim in governed.claims)
    assert "inert" in run.safety_boundary.lower()
    assert run.comparison[-1].changed is True


@pytest.mark.parametrize(
    ("approval_state", "expected_code", "expected_counter"),
    [
        ("missing", "CROSSING_APPROVAL_REQUIRED", (0, 0)),
        ("valid", "ALLOWED", (0, 0)),
        ("expired", "APPROVAL_STALE", (0, 0)),
        ("non_human", "APPROVAL_NON_HUMAN", (0, 0)),
        ("wrong_revision", "APPROVAL_REVISION_MISMATCH", (0, 0)),
    ],
)
def test_real_approval_assertion_variants(
    approval_state: str,
    expected_code: str,
    expected_counter: tuple[int, int],
) -> None:
    run = scenarios.run_atlas_demo(DemoOptions(approval_state=approval_state))
    governed = _variant(run, "governed")
    publication = _counter(run, "governed")

    crossing = _decision(run, "governed", capability="cross_zone_publication")
    assert crossing.code == expected_code
    assert crossing.approval_state == approval_state
    assert (publication.attempts, publication.completions) == expected_counter
    assert _decision(run, "governed", capability="publish_external").code == "CAPABILITY_DENIED"
    assert governed.evidence.validation_status == EvidenceStatus.PASS
    assert all(
        event["subject_revision"] == LAB_SUBJECT_REVISION for event in governed.evidence.events
    )


def test_valid_crossing_approval_does_not_mutate_generic_capability_authority() -> None:
    run = scenarios.run_atlas_demo(DemoOptions(approval_state="valid"))
    assert _decision(run, "governed", capability="cross_zone_publication").code == "ALLOWED"
    assert (_counter(run, "governed").attempts, _counter(run, "governed").completions) == (0, 0)
    assert any(
        claim.status == ClaimStatus.UNSUPPORTED and "mutated" in claim.claim
        for claim in _variant(run, "governed").claims
    )

    atlas = shared_contract("atlas")
    authorizer = load_authorizer(
        atlas / "network.nyx",
        atlas / "nornyx.agentic_network.lock",
        validation_as_of=LAB_AS_OF,
    )
    generic = authorizer.evaluate(
        CapabilityRequest("identity.research_assistant", "publish_external"),
        context=EvaluationContext(
            decision_at=LAB_AS_OF,
            observed_subject_revision=LAB_SUBJECT_REVISION,
        ),
    )
    assert generic.allowed is False
    assert generic.code.value == "CAPABILITY_DENIED"


def test_revision_and_identity_options_are_real_fail_closed_decisions() -> None:
    revision = scenarios.run_atlas_demo(DemoOptions(observed_subject_revision="git:" + "f" * 40))
    governed = _variant(revision, "governed")
    assert {item.code for item in governed.decisions} == {"REVISION_MISMATCH"}
    assert governed.evidence.validation_status == EvidenceStatus.MISSING
    assert governed.evidence.findings[0].code == "EVIDENCE_BINDING_REFUSED"
    assert _counter(revision, "governed").meaning == CounterMeaning.PREVENTED

    identity = scenarios.run_atlas_demo(DemoOptions(identity_ref="identity.not_declared"))
    assert {item.code for item in _variant(identity, "governed").decisions} == {"REQUEST_MALFORMED"}
    assert (
        _counter(identity, "governed").attempts,
        _counter(identity, "governed").completions,
    ) == (
        0,
        0,
    )


@pytest.mark.parametrize(
    ("failure_mode", "expected_code", "expected_counter"),
    [
        ("fail_closed", "ENFORCEMENT_FAILURE_FAIL_CLOSED", (0, 0)),
        ("fail_open", "ENFORCEMENT_FAILURE_FAIL_OPEN", (1, 1)),
        ("bounded", "ENFORCEMENT_FAILURE_BOUNDED_BLOCK", (0, 0)),
    ],
)
def test_enforcement_failure_modes_are_labeled_as_application_behavior(
    failure_mode: str,
    expected_code: str,
    expected_counter: tuple[int, int],
) -> None:
    run = scenarios.run_atlas_demo(DemoOptions(enforcement_failure=True, failure_mode=failure_mode))
    governed = _variant(run, "governed")
    counter = _counter(run, "governed")
    assert governed.decisions[0].code == expected_code
    assert governed.decisions[0].effect == "error"
    assert (counter.attempts, counter.completions) == expected_counter
    assert governed.evidence.validation_status == EvidenceStatus.MISSING
    assert "application" in governed.decisions[0].reason.lower()


def test_disabled_enforcement_and_clean_context_are_not_mislabeled_as_prevention() -> None:
    disabled = scenarios.run_atlas_demo(DemoOptions(enforcement_enabled=False))
    assert _variant(disabled, "governed").decisions[0].code == "ENFORCEMENT_DISABLED"
    assert (
        _counter(disabled, "governed").attempts,
        _counter(disabled, "governed").completions,
    ) == (
        1,
        1,
    )

    clean = scenarios.run_atlas_demo(DemoOptions(injection_enabled=False))
    assert _counter(clean, "ungoverned").meaning == CounterMeaning.NOT_PLANNED
    assert _counter(clean, "governed").meaning == CounterMeaning.NOT_PLANNED
    assert not _variant(clean, "governed").decisions
    assert "not planned" in _variant(clean, "governed").claims[0].limitation.lower()


def test_demo_is_byte_for_byte_deterministic_at_the_typed_boundary() -> None:
    options = DemoOptions(approval_state="expired")
    first = scenarios.run_atlas_demo(options)
    second = scenarios.run_atlas_demo(options)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_live_mode_is_never_silently_replaced() -> None:
    with pytest.raises(scenarios.ScenarioUnavailable, match="never substituted silently"):
        scenarios.run_atlas_demo(DemoOptions(planner_mode="live"))


def test_injected_live_planner_is_called_once_and_governance_stays_identical() -> None:
    class FakeLivePlanner:
        model = "test-live-model"

        def __init__(self) -> None:
            self.calls = 0

        def plan(self, task: str, context: str = "") -> Plan:
            self.calls += 1
            return Plan(
                calls=(
                    ToolCall("search_web", {"query": task}, "live proposal"),
                    ToolCall("draft_briefing", {"topic": task}, "live proposal"),
                    ToolCall("publish_external", {"source": "context"}, "live proposal"),
                ),
                answer="captured fake live plan",
            )

    planner = FakeLivePlanner()
    run = scenarios.run_atlas_demo(
        DemoOptions(planner_mode="live"),
        planner=planner,
    )

    assert planner.calls == 1
    assert run.deterministic is False
    assert run.planner_input.planner_kind == "live_model"
    assert run.planner_input.model == "test-live-model"
    assert (_counter(run, "ungoverned").attempts, _counter(run, "ungoverned").completions) == (
        1,
        1,
    )
    assert (_counter(run, "governed").attempts, _counter(run, "governed").completions) == (
        0,
        0,
    )
    assert _decision(run, "governed", capability="cross_zone_publication").code == (
        "CROSSING_APPROVAL_REQUIRED"
    )
    assert any(
        claim.status == ClaimStatus.UNSUPPORTED and "reproduce" in claim.claim
        for claim in _variant(run, "governed").claims
    )
    assert "may differ" in run.residual_risk
