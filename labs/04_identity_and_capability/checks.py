"""Concept checks for Lab 04."""

from __future__ import annotations

import pytest
from nornyx.agentic import (
    CapabilityRequest,
    DelegationRequest,
    EvaluationContext,
    HandoffRequest,
    IdentityResolutionError,
)

from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract

CONTRACT = shared_contract("ledger")


def _az():
    return authorizer_for(CONTRACT)


def _ctx():
    return EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)


def test_one_identity_is_reachable_from_several_framework_names():
    """The same governance subject, however the framework spells it."""
    az = _az()
    assert az.resolve_identity("crewai", "remediation_agent") == "identity.remediation_agent"
    assert az.resolve_identity("langgraph", "remediator") == "identity.remediation_agent"


def test_an_unmapped_runtime_name_fails_closed():
    """Not a denial — a refusal to guess who is acting."""
    az = _az()
    with pytest.raises(IdentityResolutionError) as exc:
        az.resolve_identity("crewai", "helpful_intern")
    assert exc.value.code.value


def test_capability_is_held_per_identity_not_per_role_string():
    az, ctx = _az(), _ctx()
    analyst_can = az.evaluate(
        CapabilityRequest("identity.case_analyst", "propose_refund"), context=ctx
    )
    intake_cannot = az.evaluate(
        CapabilityRequest("identity.intake_agent", "propose_refund"), context=ctx
    )
    assert analyst_can.allowed
    assert not intake_cannot.allowed
    assert intake_cannot.code.value == "CAPABILITY_DENIED"


def test_the_request_type_determines_what_is_being_asked():
    """Holding a capability and being allowed to cross with it are separate.

    `CapabilityRequest` answers "does this identity hold this?" — and for the
    declared holder the answer is yes. The gate and approval attached to
    `issue_refund` bind the boundary crossing, which is a different request.
    An adapter that asks only the first question has wired up half a gate.
    """
    from nornyx.agentic import ZoneCrossingRequest

    az, ctx = _az(), _ctx()
    holder = "identity.remediation_agent"

    holds = az.evaluate(CapabilityRequest(holder, "issue_refund"), context=ctx)
    assert holds.allowed, "the declared holder does hold it"

    crossing = az.evaluate(
        ZoneCrossingRequest(holder, "zone.remediation_internal", "zone.customer_channel"),
        context=ctx,
    )
    assert not crossing.allowed
    assert crossing.code.value == "CROSSING_APPROVAL_REQUIRED", (
        "the gate on the customer channel demands a human approval"
    )


def test_an_undeclared_zone_transition_is_denied_outright():
    """remediation_internal declares one legal target, and it is not itself."""
    from nornyx.agentic import ZoneCrossingRequest

    az, ctx = _az(), _ctx()
    decision = az.evaluate(
        ZoneCrossingRequest(
            "identity.remediation_agent",
            "zone.remediation_internal",
            "zone.remediation_internal",
        ),
        context=ctx,
    )
    assert decision.code.value == "ZONE_CROSSING_DENIED"


def test_default_deny_on_an_undeclared_capability():
    az, ctx = _az(), _ctx()
    decision = az.evaluate(CapabilityRequest("identity.case_analyst", "wire_transfer"), context=ctx)
    assert decision.code.value == "CAPABILITY_UNKNOWN"


def test_delegation_and_handoff_are_separately_typed_decisions():
    az, ctx = _az(), _ctx()
    delegation = az.evaluate(DelegationRequest("delegation.refund_proposal"), context=ctx)
    handoff = az.evaluate(HandoffRequest("handoff.compliance_closure"), context=ctx)

    assert delegation.allowed, "the declared, in-window, depth-bounded delegation holds"
    assert handoff.code.value, "the handoff is evaluated on its own terms"

    # An undeclared delegation is not silently permitted.
    ghost = az.evaluate(DelegationRequest("delegation.does_not_exist"), context=ctx)
    assert not ghost.allowed


def test_the_delegation_declares_a_depth_bound():
    """Depth is what keeps a chain from growing past what anyone reviewed."""
    text = (CONTRACT / "network.nyx").read_text(encoding="utf-8")
    assert "max_depth: 1" in text
    assert "onward_delegation: denied" in text
