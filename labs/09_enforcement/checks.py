"""Concept checks for Lab 09."""

from __future__ import annotations

from nornyx.agentic import CapabilityRequest, EvaluationContext

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.ledger import Ledger

ID = "identity.case_analyst"


class BrokenAuthorizer:
    def evaluate(self, request, *, context):
        raise RuntimeError("policy evaluation unavailable")


def _ctx():
    return EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)


def _guarded(authorizer, ledger: Ledger, *, fail_open: bool) -> None:
    try:
        decision = authorizer.evaluate(CapabilityRequest(ID, "issue_refund"), context=_ctx())
    except Exception:
        ledger.decision("EVALUATION_UNAVAILABLE", "allow" if fail_open else "deny")
        if fail_open:
            northstar.issue_refund(ledger, 5000.0)
        return
    ledger.decision(decision.code.value, decision.effect.value)
    if decision.allowed:
        northstar.issue_refund(ledger, 5000.0)


def test_the_healthy_engine_denies_and_nothing_runs():
    ledger = Ledger("healthy")
    _guarded(authorizer_for(shared_contract("ledger")), ledger, fail_open=False)

    assert ledger.completions("issue_refund") == 0
    assert ledger.codes() == ["CAPABILITY_DENIED"]


def test_fail_open_turns_an_outage_into_a_disbursement():
    ledger = Ledger("fail-open")
    _guarded(BrokenAuthorizer(), ledger, fail_open=True)

    assert ledger.completions("issue_refund") == 1, (
        "this is the defect: the guard being down became a grant"
    )
    assert ledger.codes() == ["EVALUATION_UNAVAILABLE"]


def test_fail_closed_turns_the_same_outage_into_a_refusal():
    ledger = Ledger("fail-closed")
    _guarded(BrokenAuthorizer(), ledger, fail_open=False)

    assert ledger.attempts("issue_refund") == 0
    assert ledger.completions("issue_refund") == 0


def test_the_outage_is_recorded_either_way():
    """A degraded decision that leaves no trace is worse than a denial."""
    for fail_open in (True, False):
        ledger = Ledger(f"fail_open={fail_open}")
        _guarded(BrokenAuthorizer(), ledger, fail_open=fail_open)
        assert "EVALUATION_UNAVAILABLE" in ledger.codes()


def test_the_authorizer_load_path_is_itself_fail_closed():
    """Not just evaluation — construction refuses rather than degrading."""
    from nornyx.agentic import AuthorizerLoadError, load_authorizer

    contract = shared_contract("ledger")
    try:
        load_authorizer(
            contract / "network.nyx",
            contract / "missing.lock",
            validation_as_of=LAB_AS_OF,
        )
    except AuthorizerLoadError as exc:
        assert exc.code.value in {"LOCK_INVALID", "LOCK_STALE"}
    else:
        raise AssertionError("a missing lock must not produce a usable authorizer")


def test_a_bounded_fallback_permits_only_its_allowlist():
    """Degraded mode is narrow, recorded, and never covers the risky action."""
    DEGRADED_ALLOWLIST = {"read_customer_case"}

    def bounded(action: str, ledger: Ledger) -> None:
        try:
            raise RuntimeError("policy evaluation unavailable")
        except Exception:
            if action in DEGRADED_ALLOWLIST:
                ledger.decision("DEGRADED_MODE_GRANT", "allow", action=action)
                northstar.read_case(ledger, "CASE-1041")
            else:
                ledger.decision("EVALUATION_UNAVAILABLE", "deny", action=action)

    safe, risky = Ledger("degraded-safe"), Ledger("degraded-risky")
    bounded("read_customer_case", safe)
    bounded("issue_refund", risky)

    assert safe.completions("read_case") == 1
    assert risky.completions("issue_refund") == 0
    assert risky.attempts("issue_refund") == 0
    assert safe.codes() == ["DEGRADED_MODE_GRANT"], "the grant is recorded as degraded"
