"""Concept checks for Lab 22."""

from __future__ import annotations

from nornyx.agentic import (
    ApprovalAssertion,
    CapabilityRequest,
    DelegationRequest,
    EvaluationContext,
    EvidenceRecorder,
    ZoneCrossingRequest,
)

from nornyx_lab import northstar
from nornyx_lab.constants import (
    APPROVAL_EXPIRES_AT,
    APPROVAL_ISSUED_AT,
    LAB_AS_OF,
    LAB_SUBJECT_REVISION,
)
from nornyx_lab.contract import authorizer_for, shared_contract

LEDGER = shared_contract("ledger")


def _az():
    return authorizer_for(LEDGER)


def _ctx():
    return EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)


def test_no_single_identity_can_complete_a_refund_alone():
    """Separation of duties, expressed over identities and capabilities."""
    az, ctx = _az(), _ctx()

    # The analyst may propose, not issue.
    assert az.evaluate(
        CapabilityRequest("identity.case_analyst", "propose_refund"), context=ctx
    ).allowed
    assert not az.evaluate(
        CapabilityRequest("identity.case_analyst", "issue_refund"), context=ctx
    ).allowed

    # The remediation agent holds issue_refund but cannot cross to the customer
    # channel without a human approval.
    assert az.evaluate(
        CapabilityRequest("identity.remediation_agent", "issue_refund"), context=ctx
    ).allowed
    crossing = az.evaluate(
        ZoneCrossingRequest(
            "identity.remediation_agent",
            "zone.remediation_internal",
            "zone.customer_channel",
        ),
        context=ctx,
    )
    assert crossing.effect.value == "approval_required"


def test_no_agent_identity_can_approve():
    """`can_approve: false` on every identity, including the compliance officer.

    Asserted against the parsed document rather than the raw text: a prose
    comment mentioning the field would otherwise satisfy a substring count, and
    a governance check that a comment can satisfy is not a check.
    """
    from nornyx.parser import load_nyx

    identities = load_nyx(LEDGER / "network.nyx")["agent_identities"]
    assert len(identities) == 4

    for identity in identities:
        assert identity["can_approve"] is False, f"{identity['id']} may approve"
        assert identity["authority"] == "non_human"


def test_the_compliance_officer_may_request_but_not_grant():
    az, ctx = _az(), _ctx()
    assert az.evaluate(
        CapabilityRequest("identity.compliance_officer", "request_human_approval"), context=ctx
    ).allowed
    assert not az.evaluate(
        CapabilityRequest("identity.compliance_officer", "issue_refund"), context=ctx
    ).allowed


def test_the_delegation_is_bounded_on_four_axes():
    az, ctx = _az(), _ctx()
    assert az.evaluate(DelegationRequest("delegation.refund_proposal"), context=ctx).allowed

    text = (LEDGER / "network.nyx").read_text(encoding="utf-8")
    block = text[text.index("    - id: delegation.refund_proposal") :]
    block = block[: block.index("  handoffs:")]
    for bound in ("capability_ref:", "scope_refs:", "expires_at:", "max_depth: 1"):
        assert bound in block, f"delegation is not bounded by {bound}"
    assert "onward_delegation: denied" in block


def test_escalation_resolves_when_the_named_human_approves():
    az, ctx = _az(), _ctx()
    approval = ApprovalAssertion(
        approval_ref="agentic_network_authority",
        claimed_approver_ref="human.network_governance_owner",
        claimed_actor_type="human",
        role="network_governance_owner",
        granted=True,
        action_ref="notify_customer",
        subject_revision=LAB_SUBJECT_REVISION,
        issued_at=APPROVAL_ISSUED_AT,
        expires_at=APPROVAL_EXPIRES_AT,
        evidence_refs=("approval_record", "agentic_network_contract_review"),
    )
    decision = az.evaluate(
        ZoneCrossingRequest(
            "identity.remediation_agent",
            "zone.remediation_internal",
            "zone.customer_channel",
            approval,
        ),
        context=ctx,
    )
    assert decision.allowed


def test_an_incident_is_reconstructible_from_the_artifacts():
    """The seven-step chain, exercised end to end."""
    az, ctx = _az(), _ctx()
    recorder = EvidenceRecorder(az, ctx, producer_id="nornyx-lab.ops")
    mission = "mission.incident-4471"

    from nornyx_lab.ledger import Ledger

    ledger = Ledger("incident")
    allowed = az.evaluate(
        CapabilityRequest("identity.intake_agent", "read_customer_case"), context=ctx
    )
    recorder.record_decision(allowed, mission_id=mission)
    northstar.read_case(ledger, "CASE-1041")
    recorder.record_observation(
        "tool_invoked",
        mission_id=mission,
        actor_ref="identity.intake_agent",
        capability_ref="read_customer_case",
    )
    denied = az.evaluate(CapabilityRequest("identity.intake_agent", "issue_refund"), context=ctx)
    recorder.record_decision(denied, mission_id=mission)

    report = recorder.validate()
    assert report["status"] == "pass"
    assert report["contract_digest"].startswith("sha256:")
    assert report["network_lock_digest"].startswith("sha256:")
    assert report["subject_revision"] == LAB_SUBJECT_REVISION
    assert report["counts_by_type"].get("capability_denied", 0) >= 1

    # And the ledger independently records that only the allowed work happened.
    assert ledger.completions("read_case") == 1
    assert ledger.completions("issue_refund") == 0


def test_reconstruction_cannot_establish_that_the_approver_reviewed_anything():
    """Where step 7 stops. Stated as a test so nobody forgets it."""
    az, ctx = _az(), _ctx()
    recorder = EvidenceRecorder(az, ctx, producer_id="nornyx-lab.ops")
    recorder.record_decision(
        az.evaluate(CapabilityRequest("identity.intake_agent", "read_customer_case"), context=ctx),
        mission_id="mission.limits",
    )
    limitations = " ".join(recorder.validate().get("limitations", [])).lower()
    assert "not event truth" in limitations or "does not observe" in limitations
