"""Lab 09 — Enforcement models and fail-closed design.

Where you put the check decides what it can promise. Then: break the checker on
purpose and find out what your system does when its own guard is down.
"""

from __future__ import annotations

from nornyx.agentic import CapabilityRequest, EvaluationContext

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.engine import LabContext
from nornyx_lab.ledger import Ledger

ID = "identity.case_analyst"


class BrokenAuthorizer:
    """An authorizer that is down. The most under-tested component in the stack."""

    def evaluate(self, request, *, context):
        raise RuntimeError("policy evaluation unavailable")


def run(ctx: LabContext) -> None:
    az = authorizer_for(shared_contract("ledger"))
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )

    # ------------------------------------------------------------ placement
    ctx.section("Six placements, ordered by what they can promise")

    ctx.say(
        """
From richest semantics to strongest compulsion. Nothing here is a ranking — the
top of the list knows the most about *why*, the bottom is hardest to avoid.

| # | placement | bypassable by | evidence quality | identity needed |
|---|---|---|---|---|
| 1 | **in-agent check** (the agent calls the policy itself) | the agent, trivially | self-reported | none |
| 2 | **framework adapter** (wraps the tool surface) | code in the same process | good, still self-reported | framework binding |
| 3 | **library/SDK boundary** | anything not using the SDK | good | process |
| 4 | **sidecar / local proxy** | raw sockets, other egress | independent-ish | workload |
| 5 | **network egress gateway** | nothing on that path | independent | network + workload |
| 6 | **platform IAM / sandbox** | nothing in-process | independent, strongest | platform |

Nornyx's adapters live at **row 2**. That is a cooperative boundary: it sees
rich semantics — which capability, which zone, which approval — and it can be
bypassed by code running beside it. Rows 5 and 6 cannot be talked out of it, and
know almost nothing about why.

The mature answer is not to pick one. It is to put the decision at row 2 where
the semantics are, and the compulsion at rows 5–6 where the path is — and to be
precise about which one your claim rests on.
"""
    )

    # ---------------------------------------------------------- injection
    ctx.section("Failure injection: break the guard on purpose")

    ctx.say(
        "Most systems are tested for *denied* and *allowed*. Very few are tested "
        "for **the policy engine is down**. That third case is the one that decides "
        "what your enforcement point actually guarantees."
    )

    def guarded(authorizer, ledger: Ledger, *, fail_open: bool) -> str:
        """One protected call. The `except` branch is the entire design decision."""
        try:
            decision = authorizer.evaluate(CapabilityRequest(ID, "issue_refund"), context=eval_ctx)
        except Exception:
            ledger.decision("EVALUATION_UNAVAILABLE", "allow" if fail_open else "deny")
            if not fail_open:
                return "refused: cannot evaluate"
            return northstar.issue_refund(ledger, 5000.0)
        ledger.decision(decision.code.value, decision.effect.value)
        if not decision.allowed:
            return f"refused: {decision.code.value}"
        return northstar.issue_refund(ledger, 5000.0)

    ctx.code(
        """try:
    decision = authorizer.evaluate(request, context=ctx)
except Exception:
    # fail-open : the outage silently becomes a GRANT
    # fail-closed: the outage becomes a REFUSAL
    ...""",
        caption="the branch most codebases leave implicit",
    )

    healthy = ctx.ledger("engine healthy")
    guarded(az, healthy, fail_open=False)

    open_ledger = ctx.ledger("engine down, fail-open")
    guarded(BrokenAuthorizer(), open_ledger, fail_open=True)

    closed_ledger = ctx.ledger("engine down, fail-closed")
    guarded(BrokenAuthorizer(), closed_ledger, fail_open=False)

    ctx.compare(open_ledger, closed_ledger, actions=["issue_refund"])

    ctx.decisions(
        [
            ("engine healthy", "deny", healthy.codes()[0]),
            ("engine down, fail-open", "allow", open_ledger.codes()[0]),
            ("engine down, fail-closed", "deny", closed_ledger.codes()[0]),
        ],
        "the same request under three conditions",
    )
    ctx.record("fail_open_completions", open_ledger.completions("issue_refund"))
    ctx.record("fail_closed_completions", closed_ledger.completions("issue_refund"))
    ctx.record("healthy_code", healthy.codes()[0])

    ctx.verdict(
        closed_ledger.completions("issue_refund") == 0
        and open_ledger.completions("issue_refund") == 1,
        "An outage in the governance layer became a 5000.00 disbursement in one "
        "design and a refusal in the other. Nobody chose this at 3am — it was "
        "chosen months earlier, by whoever wrote the except branch.",
    )

    ctx.concept(
        "failure behaviour is part of the guarantee",
        """
"Atlas cannot publish without approval" is incomplete until you can answer *and
when the approval service is unreachable?*

If the answer is "it publishes", the original sentence was false the whole time —
it just happened to be true while everything worked. Chapter 10's formulation:
the failure mode of an enforcing component is part of its guarantee, not an
operational detail to be worked out later.
""",
    )

    # ------------------------------------------------------- bounded fallback
    ctx.section("Fail-closed does not mean 'never move'")

    ctx.say(
        """
Absolute fail-closed has a failure mode of its own: the policy engine goes down,
the business stops, and someone disables governance entirely to restore service.
Now you have no enforcement *and* no record.

The design that survives contact with an incident is a **bounded, accountable
fallback**:

- **bounded** — a named, narrow set of actions may proceed degraded; the rest do not
- **accountable** — every degraded action is recorded as such, with who invoked it
- **expiring** — the degraded mode dies on a timer, not on someone remembering
- **loud** — entering it pages a human; it is an incident, not a mode

That is exactly the bounded-exception pattern from Lab 08, applied to
availability instead of policy.
"""
    )

    ctx.code(
        """except EvaluationUnavailable:
    if action in DEGRADED_ALLOWLIST and emergency.active(now):
        ledger.decision("DEGRADED_MODE_GRANT", "allow",
                        invoked_by=emergency.owner, expires=emergency.expires_at)
        page_oncall("governance degraded-mode grant", action=action)
        return perform(action)
    ledger.decision("EVALUATION_UNAVAILABLE", "deny")
    raise""",
        caption="bounded, accountable, expiring, loud",
    )

    ctx.boundary(
        """
**A fail-closed adapter is still row 2.** It refuses when it cannot evaluate —
and it is still reached only by code that chose to call it.

Failing closed protects you from *your own outage*. It does not protect you from
an attacker who never invokes the wrapper at all. That is a coverage problem,
and coverage is Lab 13.
"""
    )

    ctx.tryit(
        """
1. Find one `try/except` in your own codebase that wraps an authorization call.
   Which branch does the `except` take? Was that written deliberately?
2. Add a third mode to `guarded()` — a bounded fallback that permits
   `read_customer_case` but never `issue_refund` while the engine is down. What
   must it record for the action to be defensible afterwards?
"""
    )
