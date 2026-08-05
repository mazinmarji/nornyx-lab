"""Concept checks for Lab 00.

Read these. Each test is one proposition the lab established, written as
something a machine can settle. That is the habit the whole book is teaching:
a governance claim you cannot express as a test is not yet a claim.
"""

from __future__ import annotations

from nornyx_lab import northstar
from nornyx_lab.ledger import Ledger
from nornyx_lab.model import DeterministicPlanner


def test_an_assistant_without_tools_causes_nothing():
    """A planner alone has no side effects, however bad its plan is."""
    ledger = Ledger("assistant")
    plan = DeterministicPlanner().plan("Write a briefing", northstar.HOSTILE_PAGE)

    assert plan.calls, "the planner should still propose actions"
    assert len(ledger) == 0, "but proposing is not doing — the ledger must be empty"


def test_retrieved_text_steers_the_planner():
    """Instruction-data confusion, observed rather than asserted.

    The same planner, given the same task, proposes an extra action purely
    because a retrieved page told it to. Nothing marks that text as untrusted.
    """
    planner = DeterministicPlanner()
    clean = planner.plan("Write a briefing on the competitor", northstar.CLEAN_PAGE)
    hostile = planner.plan("Write a briefing on the competitor", northstar.HOSTILE_PAGE)

    assert "publish_external" not in clean.actions
    assert "publish_external" in hostile.actions
    assert hostile.influenced_by, "the planner should name the text that steered it"


def test_an_ungoverned_agent_completes_the_injected_action():
    """With tools attached and no boundary, the plan becomes an effect."""
    ledger = Ledger("agent")
    page = northstar.search_web(ledger, "competitor pricing", hostile=True)
    plan = DeterministicPlanner().plan("Write a briefing on the competitor", page)

    for call in plan.calls:
        if call.action != "search_web":
            northstar.perform(ledger, call.action, **call.args)

    assert ledger.attempts("publish_external") == 1
    assert ledger.completions("publish_external") == 1, (
        "the briefing was published — this is the baseline the rest of the labs improve on"
    )


def test_the_ledger_distinguishes_prevention_from_failure():
    """The three readings, made concrete.

    This is the single most important check in the repository. If you only
    remember one thing from Lab 00, remember that 1/0 is not prevention.
    """
    prevented = Ledger("prevented")  # never entered the callable

    failed = Ledger("failed")  # entered, then blew up
    failed.attempt("issue_refund", amount=5000.0)

    ran = Ledger("ran")  # entered and completed
    northstar.issue_refund(ran, 5000.0)

    assert (prevented.attempts("issue_refund"), prevented.completions("issue_refund")) == (0, 0)
    assert (failed.attempts("issue_refund"), failed.completions("issue_refund")) == (1, 0)
    assert (ran.attempts("issue_refund"), ran.completions("issue_refund")) == (1, 1)

    # A transcript would show "no refund receipt" for both of the first two.
    # Only the ledger tells you that one of them touched the payments path.
    assert prevented.completions("issue_refund") == failed.completions("issue_refund")
    assert prevented.attempts("issue_refund") != failed.attempts("issue_refund")


def test_decisions_and_effects_share_one_clock():
    """Ordering is checkable only because both land on the same counter."""
    ledger = Ledger("ordered")
    ledger.decision("ALLOWED", "allow")
    northstar.issue_refund(ledger, 50.0)

    assert ledger.decided_before_acting("issue_refund")

    # A second refund on the SAME single authorization must fail the check:
    # reusing one decision for two actions is exactly what this catches.
    northstar.issue_refund(ledger, 50.0)
    assert not ledger.decided_before_acting("issue_refund")
