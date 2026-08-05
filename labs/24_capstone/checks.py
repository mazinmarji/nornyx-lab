"""Concept checks for Lab 24 — the failure-injection programme, verified.

This file is the repository's own verification matrix. If any test here fails,
a claim in `claim_register.json` has become false.
"""

from __future__ import annotations

import pytest
from nornyx.agentic import (
    ApprovalAssertion,
    AuthorizerLoadError,
    CapabilityRequest,
    EvaluationContext,
    EvidenceRecorder,
    ZoneCrossingRequest,
    load_authorizer,
)

from nornyx_lab import northstar
from nornyx_lab.constants import (
    APPROVAL_EXPIRES_AT,
    APPROVAL_ISSUED_AT,
    LAB_AS_OF,
    LAB_SUBJECT_REVISION,
)
from nornyx_lab.contract import authorizer_for, lock_check, nornyx, shared_contract
from nornyx_lab.ledger import Ledger

ATLAS = shared_contract("atlas")
LEDGER = shared_contract("ledger")
ID = "identity.research_assistant"
INTERNAL, PUBLIC = "zone.research_internal", "zone.public_web"


def _ctx(revision: str = LAB_SUBJECT_REVISION):
    return EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=revision)


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


# ------------------------------------------------------------------- the build
@pytest.mark.parametrize("contract", [ATLAS, LEDGER], ids=["atlas", "ledger"])
def test_every_contract_passes_every_design_time_gate(contract):
    assert nornyx("check", "network.nyx", "--as-of", LAB_AS_OF, cwd=contract).ok
    assert lock_check(
        contract / "network.nyx",
        contract / "nornyx.agentic_network.lock",
        contract / "control_artifacts",
        cwd=contract,
    ).ok


# ------------------------------------------------------ failure injection 1-8
@pytest.mark.parametrize(
    ("label", "request_factory", "expected"),
    [
        (
            "unheld capability",
            lambda: CapabilityRequest(ID, "publish_external"),
            "CAPABILITY_DENIED",
        ),
        (
            "undeclared capability",
            lambda: CapabilityRequest(ID, "wire_transfer"),
            "CAPABILITY_UNKNOWN",
        ),
        (
            "crossing without approval",
            lambda: ZoneCrossingRequest(ID, INTERNAL, PUBLIC),
            "CROSSING_APPROVAL_REQUIRED",
        ),
        (
            "AI approval",
            lambda: ZoneCrossingRequest(
                ID, INTERNAL, PUBLIC, _approval(claimed_actor_type="ai_tool")
            ),
            "APPROVAL_NON_HUMAN",
        ),
        (
            "wrong revision",
            lambda: ZoneCrossingRequest(
                ID, INTERNAL, PUBLIC, _approval(subject_revision="git:" + "0" * 40)
            ),
            "APPROVAL_REVISION_MISMATCH",
        ),
        (
            "stale approval",
            lambda: ZoneCrossingRequest(
                ID,
                INTERNAL,
                PUBLIC,
                _approval(issued_at="2026-01-01T00:00:00Z", expires_at="2026-01-08T00:00:00Z"),
            ),
            "APPROVAL_STALE",
        ),
    ],
)
def test_injected_failure_is_refused_with_its_own_code(label, request_factory, expected):
    decision = authorizer_for(ATLAS).evaluate(request_factory(), context=_ctx())
    assert not decision.allowed, label
    assert decision.code.value == expected, f"{label}: got {decision.code.value}"


def test_injected_failure_7_deployment_revision_skew():
    decision = authorizer_for(ATLAS).evaluate(
        CapabilityRequest(ID, "search_web"), context=_ctx("git:" + "0" * 40)
    )
    assert decision.code.value == "REVISION_MISMATCH"


def test_injected_failure_8_substituted_lock():
    try:
        load_authorizer(
            ATLAS / "network.nyx",
            LEDGER / "nornyx.agentic_network.lock",
            validation_as_of=LAB_AS_OF,
        )
    except AuthorizerLoadError as exc:
        assert exc.code.value in {"LOCK_STALE", "LOCK_INVALID"}
    else:
        raise AssertionError("a lock from another contract must not load")


# ---------------------------------------------------------- failure 9: honest
def test_injected_failure_9_direct_invocation_is_NOT_mitigated():
    """The row that makes the matrix honest.

    If a future change closes this — an independent boundary, a separate
    process — rewrite this test to assert prevention. That rewrite is the moment
    claim NS-001's tier changes, and it should be reviewed as such.
    """
    ledger = Ledger("bypass")
    northstar.issue_refund(ledger, 5000.0)

    assert ledger.completions("issue_refund") == 1
    assert not ledger.codes(), "no decision was consulted — nothing was asked"


# ------------------------------------------------------------ the happy path
def test_the_governed_happy_path_still_works():
    """Governance is not a machine for saying no."""
    az = authorizer_for(ATLAS)
    ctx = _ctx()
    ledger = Ledger("approved")

    decision = az.evaluate(ZoneCrossingRequest(ID, INTERNAL, PUBLIC, _approval()), context=ctx)
    ledger.decision(decision.code.value, decision.effect.value)
    if decision.allowed:
        northstar.publish_external(ledger, "briefing")

    assert decision.allowed
    assert ledger.completions("publish_external") == 1
    assert ledger.decided_before_acting("publish_external")


def test_the_full_evidence_stream_validates():
    az = authorizer_for(ATLAS)
    ctx = _ctx()
    recorder = EvidenceRecorder(az, ctx, producer_id="nornyx-lab.capstone")
    for capability in ("search_web", "publish_external"):
        recorder.record_decision(
            az.evaluate(CapabilityRequest(ID, capability), context=ctx),
            mission_id="mission.capstone",
        )
    report = recorder.validate()

    assert report["status"] == "pass"
    assert report["diagnostics"] == []
    assert report["subject_revision"] == LAB_SUBJECT_REVISION
    assert report.get("limitations"), "and it still states what it cannot prove"
