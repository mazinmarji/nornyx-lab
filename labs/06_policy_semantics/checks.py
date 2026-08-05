"""Concept checks for Lab 06."""

from __future__ import annotations

from pathlib import Path

from nornyx.agentic import (
    ApprovalAssertion,
    CapabilityRequest,
    DelegationRequest,
    EvaluationContext,
    ZoneCrossingRequest,
)

from nornyx_lab.constants import (
    APPROVAL_EXPIRES_AT,
    APPROVAL_ISSUED_AT,
    LAB_AS_OF,
    LAB_SUBJECT_REVISION,
)
from nornyx_lab.contract import authorizer_for, nornyx, shared_contract

ATLAS = shared_contract("atlas")
ID = "identity.research_assistant"
INTERNAL, PUBLIC = "zone.research_internal", "zone.public_web"


def _ctx(at: str = LAB_AS_OF):
    return EvaluationContext(decision_at=at, observed_subject_revision=LAB_SUBJECT_REVISION)


def _approval(**overrides):
    base = dict(
        approval_ref="agentic_network_authority",
        claimed_approver_ref="human.network_governance_owner",
        claimed_actor_type="human",
        role="network_governance_owner",
        granted=True,
        action_ref="publish_external",
        subject_revision=LAB_SUBJECT_REVISION,
        issued_at=APPROVAL_ISSUED_AT,
        expires_at=APPROVAL_EXPIRES_AT,
        evidence_refs=("approval_record", "agentic_network_contract_review"),
    )
    base.update(overrides)
    return ApprovalAssertion(**base)


def test_all_three_decision_values_are_reachable():
    """A two-valued engine cannot express 'not yet, and here is what is missing'."""
    az = authorizer_for(ATLAS)
    effects = {
        az.evaluate(CapabilityRequest(ID, "search_web"), context=_ctx()).effect.value,
        az.evaluate(CapabilityRequest(ID, "publish_external"), context=_ctx()).effect.value,
        az.evaluate(ZoneCrossingRequest(ID, INTERNAL, PUBLIC), context=_ctx()).effect.value,
    }
    assert effects == {"allow", "deny", "approval_required"}


def test_approval_required_resolves_to_allow_when_the_input_arrives():
    """It is 'not yet', not 'no' — supplying the named input changes the answer."""
    az = authorizer_for(ATLAS)
    without = az.evaluate(ZoneCrossingRequest(ID, INTERNAL, PUBLIC), context=_ctx())
    with_approval = az.evaluate(
        ZoneCrossingRequest(ID, INTERNAL, PUBLIC, _approval()), context=_ctx()
    )
    assert without.effect.value == "approval_required"
    assert with_approval.allowed


def test_default_deny_answers_requests_no_rule_mentions():
    az = authorizer_for(ATLAS)
    assert az.evaluate(CapabilityRequest(ID, "launch_missiles"), context=_ctx()).code.value == (
        "CAPABILITY_UNKNOWN"
    )
    assert not az.evaluate(DelegationRequest("delegation.invented"), context=_ctx()).allowed


def test_evaluation_is_deterministic_across_repetition():
    az = authorizer_for(ATLAS)
    request = CapabilityRequest(ID, "search_web")
    outcomes = {az.evaluate(request, context=_ctx()).code.value for _ in range(200)}
    assert len(outcomes) == 1


def test_two_independently_loaded_authorizers_agree():
    """Determinism across processes, not just across calls in one."""
    a = authorizer_for(ATLAS)
    b = authorizer_for(ATLAS)
    request = ZoneCrossingRequest(ID, INTERNAL, PUBLIC)
    assert a.evaluate(request, context=_ctx()).code == b.evaluate(request, context=_ctx()).code


def test_time_is_an_input_so_past_decisions_stay_reproducible():
    az = authorizer_for(ATLAS)
    on_time = az.evaluate(ZoneCrossingRequest(ID, INTERNAL, PUBLIC, _approval()), context=_ctx())
    late = az.evaluate(
        ZoneCrossingRequest(ID, INTERNAL, PUBLIC, _approval()),
        context=_ctx("2026-09-01T00:00:00Z"),
    )
    assert on_time.allowed
    assert not late.allowed
    assert late.code.value == "APPROVAL_STALE"

    # And the original answer is still reproducible afterwards.
    assert az.evaluate(
        ZoneCrossingRequest(ID, INTERNAL, PUBLIC, _approval()), context=_ctx()
    ).allowed


def test_the_top_level_schema_is_closed():
    """An unrecognised block is an error, not a silently ignored extension."""
    tmp = Path(__file__).parent / ".closed-schema-probe.nyx"
    tmp.write_text(
        (ATLAS / "network.nyx").read_text(encoding="utf-8")
        + "\nsuper_powers:\n  - name: bypass_everything\n",
        encoding="utf-8",
    )
    try:
        result = nornyx("check", str(tmp), "--as-of", LAB_AS_OF)
        assert not result.ok, "a block nobody defined must not validate"
        assert any("UNKNOWN_TOP_LEVEL_BLOCK" in c for c in result.codes()), result.codes()
    finally:
        tmp.unlink(missing_ok=True)


def test_the_authorizer_state_is_not_mutable_through_a_handed_out_view():
    """Mutable retained structures are destroyer #3; the SPI hands out copies."""
    az = authorizer_for(ATLAS)
    document = az.state.document
    document["project"] = {"name": "Hijacked"}

    assert authorizer_for(ATLAS).state.document["project"]["name"] == "NorthstarAtlas"
    assert az.state.document["project"]["name"] == "NorthstarAtlas"
