"""Concept checks for Lab 13 — the five-test rule, applied to one surface."""

from __future__ import annotations

from nornyx.agentic import CapabilityRequest, EvaluationContext

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.ledger import Ledger
from nornyx_lab.optional import skip_unless

LEDGER_CONTRACT = shared_contract("ledger")
ID = "identity.case_analyst"


def _az():
    return authorizer_for(LEDGER_CONTRACT)


def _ctx():
    return EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)


# ------------------------------------------------------------ the five tests
def test_1_allow_the_authorized_action_runs():
    az, ctx = _az(), _ctx()
    ledger = Ledger("allow")
    if az.evaluate(CapabilityRequest(ID, "read_customer_case"), context=ctx).allowed:
        northstar.read_case(ledger, "CASE-1041")

    assert ledger.attempts("read_case") == 1
    assert ledger.completions("read_case") == 1


def test_2_deny_the_unauthorized_action_causes_nothing():
    az, ctx = _az(), _ctx()
    ledger = Ledger("deny")
    if az.evaluate(CapabilityRequest(ID, "issue_refund"), context=ctx).allowed:
        northstar.issue_refund(ledger, 5000.0)

    assert ledger.attempts("issue_refund") == 0, "prevented, not merely failed"
    assert ledger.completions("issue_refund") == 0


def test_3_failure_when_the_enforcer_throws_the_action_still_does_not_happen():
    class Broken:
        def evaluate(self, request, *, context):
            raise RuntimeError("engine down")

    ledger = Ledger("failure")
    try:
        Broken().evaluate(CapabilityRequest(ID, "issue_refund"), context=_ctx())
    except Exception:
        ledger.decision("EVALUATION_UNAVAILABLE", "deny")

    assert ledger.attempts("issue_refund") == 0


def test_4_bypass_the_known_route_around_the_wrapper_is_declared():
    """We cannot close it at Tier 2. We can refuse to claim we did.

    This test documents the gap rather than pretending it is absent. If a future
    change closes it, this test should be rewritten to assert prevention — and
    that rewrite is the governance event, not a chore.
    """
    ledger = Ledger("bypass")
    northstar.issue_refund(ledger, 5000.0)  # direct call, no decision

    assert ledger.completions("issue_refund") == 1
    assert not ledger.codes(), "no decision was recorded — the engine was never asked"


def test_5_evidence_the_decision_is_recorded_bound_and_validates():
    from nornyx.agentic import EvidenceRecorder

    az, ctx = _az(), _ctx()
    rec = EvidenceRecorder(az, ctx, producer_id="nornyx-lab.coverage")
    rec.record_decision(
        az.evaluate(CapabilityRequest(ID, "issue_refund"), context=ctx),
        mission_id="mission.coverage",
    )
    report = rec.validate()

    assert report["status"] == "pass"
    assert report["event_count"] >= 1


# ------------------------------------------------------------------ coverage
def test_the_three_coverage_states_exist_as_a_public_enum():
    from nornyx_agentic_adapters import SurfaceStatus

    values = {s.value for s in SurfaceStatus}
    assert values == {"wrapped", "unsupported", "unwrapped"}, (
        "two states would collapse 'we decided not to' with 'we never looked'"
    )


def test_the_published_inventory_admits_an_uncovered_surface():
    """An inventory with no gaps is a marketing document."""
    crewai_adapter = skip_unless("nornyx_agentic_adapters.crewai_adapter", extra="crewai")
    inventory = crewai_adapter.COVERAGE_INVENTORY

    statuses = {entry.status.value for entry in inventory.entries}
    assert "wrapped" in statuses
    assert "unsupported" in statuses, (
        "the adapter must publish at least one surface it does not cover"
    )
    for entry in inventory.entries:
        assert entry.reason, f"{entry.surface} carries no explanation"


def test_the_ledger_distinguishes_prevention_from_failure_one_more_time():
    """The single assertion this entire repository rests on."""
    prevented, failed = Ledger("prevented"), Ledger("failed")
    failed.attempt("issue_refund", amount=5000.0)

    assert prevented.completions("issue_refund") == failed.completions("issue_refund") == 0
    assert prevented.attempts("issue_refund") != failed.attempts("issue_refund")
