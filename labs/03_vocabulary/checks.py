"""Concept checks for Lab 03."""

from __future__ import annotations

from nornyx.agentic import SPI_VERSION, CapabilityRequest, EvaluationContext

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.ledger import Ledger

LEDGER_CONTRACT = shared_contract("ledger")
IDENTITY = "identity.case_analyst"


def _ctx():
    return EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)


def _refund_decision():
    az = authorizer_for(LEDGER_CONTRACT)
    return az.evaluate(CapabilityRequest(IDENTITY, "issue_refund"), context=_ctx())


def test_the_pdp_denies_a_capability_the_identity_does_not_hold():
    decision = _refund_decision()
    assert not decision.allowed
    assert decision.code.value == "CAPABILITY_DENIED"


def test_a_pdp_without_a_pep_prevents_nothing():
    """The decision is right and the money still moves."""
    decision = _refund_decision()
    ledger = Ledger("PDP only")
    ledger.decision(decision.code.value, decision.effect.value)
    northstar.issue_refund(ledger, 5000.0)  # decision never consulted

    assert ledger.completions("issue_refund") == 1


def test_the_same_decision_applied_at_a_pep_prevents_the_effect():
    decision = _refund_decision()
    ledger = Ledger("PDP + PEP")
    ledger.decision(decision.code.value, decision.effect.value)
    if decision.allowed:
        northstar.issue_refund(ledger, 5000.0)

    assert ledger.attempts("issue_refund") == 0
    assert ledger.completions("issue_refund") == 0


def test_a_second_unwrapped_path_defeats_a_correct_pep():
    """Coverage, not correctness, is what fails here (Ch. 14)."""
    decision = _refund_decision()
    ledger = Ledger("bypassed")
    if decision.allowed:
        northstar.issue_refund(ledger, 5000.0)  # the wrapped path: blocked
    northstar.issue_refund(ledger, 5000.0)  # the path nobody wrapped

    assert ledger.completions("issue_refund") == 1


def test_design_time_and_runtime_are_different_tools():
    """`nornyx check` cannot deny an action; the authorizer cannot review a policy."""
    from nornyx_lab.contract import check

    result = check(LEDGER_CONTRACT / "network.nyx")
    assert result.ok, "design-time validation passes on a contract that ..."

    decision = _refund_decision()
    assert not decision.allowed, "... still denies this runtime request"


def test_the_spi_states_its_own_version_and_binding():
    """A cooperative boundary that will not tell you its version is not one."""
    az = authorizer_for(LEDGER_CONTRACT)
    assert SPI_VERSION
    assert az.subject_revision == LAB_SUBJECT_REVISION
