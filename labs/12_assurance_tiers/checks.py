"""Concept checks for Lab 12."""

from __future__ import annotations

from nornyx.agentic import CapabilityRequest, EvaluationContext, EvidenceRecorder

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.ledger import Ledger

ATLAS = shared_contract("atlas")
ID = "identity.research_assistant"


def _ctx():
    return EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)


def test_a_tier_2_claim_is_fully_supported():
    """Decision + refusal + bound, validating evidence. All of it real."""
    az = authorizer_for(ATLAS)
    ctx = _ctx()
    decision = az.evaluate(CapabilityRequest(ID, "publish_external"), context=ctx)
    assert not decision.allowed

    rec = EvidenceRecorder(az, ctx, producer_id="nornyx-lab.tiers")
    rec.record_decision(decision, mission_id="mission.tier-demo")
    report = rec.validate()

    assert report["status"] == "pass"
    assert report["diagnostics"] == []


def test_the_validator_refuses_to_assert_runtime_truth():
    """The exact sentence that caps the claim at Tier 2."""
    az = authorizer_for(ATLAS)
    ctx = _ctx()
    rec = EvidenceRecorder(az, ctx, producer_id="nornyx-lab.tiers")
    rec.record_decision(
        az.evaluate(CapabilityRequest(ID, "search_web"), context=ctx),
        mission_id="mission.tier-demo",
    )
    limitations = " ".join(rec.validate().get("limitations", [])).lower()

    assert "not event truth" in limitations or "does not observe" in limitations


def test_self_reported_evidence_cannot_detect_a_dishonest_producer():
    """The structural ceiling: the ledger and the actor share a trust domain."""
    honest = Ledger("honest")
    northstar.issue_refund(honest, 5000.0)

    dishonest = Ledger("dishonest")
    # The effect happens; this producer just declines to record it.
    _ = f"refund:acct-88213:{5000.0:.2f}"

    assert honest.completions("issue_refund") == 1
    assert dishonest.completions("issue_refund") == 0
    # From inside, the silent ledger is indistinguishable from a prevented action.
    prevented = Ledger("prevented")
    assert dishonest.to_dict()["entries"] == prevented.to_dict()["entries"]


def test_identity_is_asserted_not_authenticated():
    """Anything the caller names, the authorizer will evaluate as."""
    az = authorizer_for(ATLAS)
    resolved = az.resolve_identity("crewai", "research_assistant")

    assert resolved == "identity.research_assistant"
    # No credential, token, or proof was supplied anywhere in that call.
    # A caller free to pass any agent_key is a caller free to choose an identity.


def test_a_falsifying_observation_is_expressible():
    """Question 8: name the observation that would prove the claim false."""
    ledger = Ledger("falsifier")
    # A completed publish with no preceding recorded decision.
    northstar.publish_external(ledger, "briefing")

    assert ledger.completions("publish_external") == 1
    assert not ledger.decided_before_acting("publish_external"), (
        "this exact pattern falsifies 'Atlas cannot publish without approval'"
    )
