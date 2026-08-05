"""Concept checks for Lab 08.

The approval taxonomy, pinned. If a future Nornyx release renamed one of these
codes, this file is where you would find out.
"""

from __future__ import annotations

import pytest
from nornyx.agentic import ApprovalAssertion, EvaluationContext, ZoneCrossingRequest

from nornyx_lab.constants import (
    APPROVAL_EXPIRES_AT,
    APPROVAL_ISSUED_AT,
    LAB_AS_OF,
    LAB_SUBJECT_REVISION,
)
from nornyx_lab.contract import authorizer_for, shared_contract

ATLAS = shared_contract("atlas")
ID = "identity.research_assistant"
INTERNAL, PUBLIC = "zone.research_internal", "zone.public_web"

VALID = dict(
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


def _decide(**overrides):
    fields = dict(VALID)
    fields.update(overrides)
    az = authorizer_for(ATLAS)
    return az.evaluate(
        ZoneCrossingRequest(ID, INTERNAL, PUBLIC, ApprovalAssertion(**fields)),
        context=EvaluationContext(
            decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
        ),
    )


def test_a_fully_valid_approval_allows_the_crossing():
    """Governance says yes when the conditions are genuinely met."""
    assert _decide().allowed


@pytest.mark.parametrize(
    ("label", "override", "expected"),
    [
        ("wrong revision", {"subject_revision": "git:" + "0" * 40}, "APPROVAL_REVISION_MISMATCH"),
        ("wrong action", {"action_ref": "draft_briefing"}, "APPROVAL_ACTION_MISMATCH"),
        ("AI approver", {"claimed_actor_type": "ai_tool"}, "APPROVAL_NON_HUMAN"),
        ("ineligible role", {"role": "intern"}, "APPROVAL_ROLE_INVALID"),
        ("missing evidence", {"evidence_refs": ("approval_record",)}, "APPROVAL_EVIDENCE_MISSING"),
        (
            "issued too long ago",
            {"issued_at": "2026-01-01T00:00:00Z", "expires_at": "2026-01-08T00:00:00Z"},
            "APPROVAL_STALE",
        ),
        (
            "issued in the future",
            {"issued_at": "2026-07-01T00:00:00Z", "expires_at": "2026-07-08T00:00:00Z"},
            "APPROVAL_STALE",
        ),
        ("not granted", {"granted": False}, "APPROVAL_NOT_GRANTED"),
    ],
)
def test_each_defect_produces_its_own_refusal(label, override, expected):
    decision = _decide(**override)
    assert not decision.allowed, label
    assert decision.code.value == expected, f"{label}: got {decision.code.value}"


def test_revision_binding_is_checked_before_expiry():
    """Order is part of the interface: diagnose the right problem first.

    An approval that is BOTH for the wrong revision AND long expired must report
    the revision mismatch, so nobody wastes an outage renewing an approval that
    was never for this artifact.
    """
    decision = _decide(
        subject_revision="git:" + "0" * 40,
        issued_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-08T00:00:00Z",
    )
    assert decision.code.value == "APPROVAL_REVISION_MISMATCH"


def test_actor_type_is_checked_before_role():
    """An AI claiming a valid role is refused as non-human, not as bad-role."""
    decision = _decide(claimed_actor_type="ai_tool", role="network_governance_owner")
    assert decision.code.value == "APPROVAL_NON_HUMAN"


def test_an_ai_cannot_approve_even_with_every_other_field_perfect():
    """The rule that has no exception."""
    for actor_type in ("ai_tool", "autonomous_agent", "model", "generated_output"):
        assert _decide(claimed_actor_type=actor_type).code.value == "APPROVAL_NON_HUMAN"


def test_the_earliest_applicable_expiry_wins():
    """Assertion expiry can look fine while issued_at + P7D has already passed."""
    decision = _decide(
        issued_at="2026-01-01T00:00:00Z",
        expires_at="2026-12-31T00:00:00Z",  # looks generous, and is irrelevant
    )
    assert decision.code.value == "APPROVAL_STALE"
