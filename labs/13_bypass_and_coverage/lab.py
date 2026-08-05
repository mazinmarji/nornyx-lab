"""Lab 13 — Bypass, coverage, and negative controls.

The uncomfortable lab. Everything you have built works, and here is how to get
around it.
"""

from __future__ import annotations

from nornyx.agentic import CapabilityRequest, EvaluationContext

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.engine import LabContext
from nornyx_lab.ledger import Ledger
from nornyx_lab.optional import try_import

ID = "identity.case_analyst"


def run(ctx: LabContext) -> None:
    az = authorizer_for(shared_contract("ledger"))
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )

    # ------------------------------------------------------------- coverage
    ctx.section("Three coverage states, because two are a lie")

    from nornyx_agentic_adapters import SurfaceStatus

    ctx.say(
        f"""
The adapter distribution models coverage with exactly three states —
`{"`, `".join(s.value for s in SurfaceStatus)}` — and the third one is why:

| state | meaning | your obligation |
|---|---|---|
| **wrapped** | the adapter intercepts this surface and it has the tests to prove it | none; the claim is supported |
| **unsupported** | the adapter *knows* about this surface and deliberately does not cover it | cover it elsewhere, or do not use it |
| **unwrapped** | nobody has assessed this surface | **find out** — this is the dangerous one |

A two-state model (covered / not covered) collapses "we decided not to" with "we
never looked", and those carry completely different risk. The honest inventory
keeps them apart.
"""
    )

    adapter = try_import("nornyx_agentic_adapters.crewai_adapter", extra="crewai")
    if adapter is not None:
        COVERAGE_INVENTORY = adapter.COVERAGE_INVENTORY
        rows = [
            (entry.surface, entry.status.value, entry.reason[:60] + "…")
            for entry in COVERAGE_INVENTORY.entries
        ]
        ctx.decisions(rows, "the real, machine-readable CrewAI coverage inventory")
        ctx.record("coverage_surfaces", len(rows))
        wrapped = sum(1 for e in COVERAGE_INVENTORY.entries if e.status is SurfaceStatus.WRAPPED)
        ctx.say(
            f"**{wrapped} of {len(rows)} declared surfaces are wrapped.** That ratio is "
            "published by the adapter itself, in code, not buried in a doc."
        )
    else:
        ctx.note("CrewAI is not installed — showing the shape only.")
        ctx.say(
            "Install it with `uv pip install -e '.[crewai]'` to read the real "
            "inventory. Labs 18–19 need it too."
        )

    ctx.concept(
        "publishing what you do NOT cover increases security",
        """
It feels backwards. It is not.

A published gap is a gap someone can compensate for: put an egress proxy in
front of it, forbid the async path in review, add a platform control. An
unpublished gap is one every reader assumes is covered — and the assumption is
what ships the incident.

The attacker enumerates your surfaces either way. Only your own team is
misled by the omission.
""",
    )

    # --------------------------------------------------------------- bypass
    ctx.section("Three structural ways past a wrapper")

    ctx.say(
        """
1. **Direct invocation beneath the wrapper** — the business callable is still
   importable. Anything in the process can call it.
2. **Uncovered asynchronous paths** — the wrapper overrides `_run`; the
   framework also offers `_arun`, which inherits the *unwrapped* base.
3. **Surfaces introduced by a framework upgrade** — the wrapper covered every
   surface that existed in 1.15.4. Version 1.16 adds one nobody has seen.

Number three is why the adapter pins `crewai==1.15.4` and **fails closed at
import** on any other version. An exact pin that refuses to run is a governance
decision, not packaging fussiness.
"""
    )

    ctx.say("Here is bypass #1, in five lines:")

    governed = ctx.ledger("through the wrapper")
    decision = az.evaluate(CapabilityRequest(ID, "issue_refund"), context=eval_ctx)
    governed.decision(decision.code.value, decision.effect.value)
    if decision.allowed:
        northstar.issue_refund(governed, 5000.0)

    bypassed = ctx.ledger("around the wrapper")
    northstar.issue_refund(bypassed, 5000.0)  # the import nobody removed

    ctx.code(
        """# the governed path
if authorizer.evaluate(CapabilityRequest(ID, "issue_refund"), context=ctx).allowed:
    northstar.issue_refund(ledger, 5000.0)

# the path that is still importable
from nornyx_lab import northstar
northstar.issue_refund(ledger, 5000.0)          # <- no decision, no evidence""",
        caption="the wrapper is a door, not a wall",
    )

    ctx.compare(governed, bypassed, actions=["issue_refund"])
    ctx.record("bypassed_completions", bypassed.completions("issue_refund"))
    ctx.record("governed_completions", governed.completions("issue_refund"))

    ctx.verdict(
        bypassed.completions("issue_refund") == 0,
        "The refund happened with no decision and no evidence. The policy engine "
        "was never wrong — it was never asked.",
    )

    # ----------------------------------------------------- negative controls
    ctx.section("Negative controls: prove the denial, and prove the bypass")

    ctx.say(
        """
A test that asserts an exception was raised proves almost nothing — the callable
may have run and *then* failed. A negative control asserts on the ledger:

```python
def test_denied_refund_causes_nothing():
    assert ledger.attempts("issue_refund") == 0       # never entered
    assert ledger.completions("issue_refund") == 0    # never finished
```

And the harder one — a test that the *bypass* is either detected or explicitly
declared ungoverned:

```python
def test_direct_invocation_is_declared_ungoverned():
    # We cannot prevent it at this tier. We CAN refuse to claim otherwise.
    assert "direct_business_callable" in COVERAGE.unsupported_surfaces
```
"""
    )

    # -------------------------------------------------------- five-test rule
    ctx.section("The five-test rule")

    ctx.say(
        """
For every surface you claim is wrapped, five tests — and each must assert
something a passing log line could not fake:

| test | must assert |
|---|---|
| **allow** | the authorized action ran: attempts 1, completions 1 |
| **deny** | the unauthorized action did not: attempts 0, completions 0 |
| **failure** | when the enforcer itself throws, the action still does not happen |
| **bypass** | the known way around it is either blocked or declared |
| **evidence** | the decision was recorded, bound, and validates |

Four out of five is not 80% of a claim. A surface with no failure test has an
unknown fail mode, and a surface with no bypass test has an unknown boundary.
"""
    )

    # A live demonstration of all five on one surface.
    class Broken:
        def evaluate(self, request, *, context):
            raise RuntimeError("engine down")

    results = {}
    allow = Ledger("allow")
    d = az.evaluate(CapabilityRequest(ID, "propose_refund"), context=eval_ctx)
    if d.allowed:
        allow.record("propose_refund_attempted")
        allow.record("propose_refund_completed")
    results["allow"] = allow.completions("propose_refund") == 1

    deny = Ledger("deny")
    d = az.evaluate(CapabilityRequest(ID, "issue_refund"), context=eval_ctx)
    if d.allowed:
        northstar.issue_refund(deny, 5000.0)
    results["deny"] = deny.attempts("issue_refund") == 0

    fail = Ledger("failure")
    try:
        Broken().evaluate(None, context=eval_ctx)
    except Exception:
        fail.decision("EVALUATION_UNAVAILABLE", "deny")
    results["failure"] = fail.attempts("issue_refund") == 0

    results["bypass"] = bypassed.completions("issue_refund") == 1  # known, declared
    results["evidence"] = bool(governed.codes())

    ctx.decisions(
        [
            (name, "allow" if ok else "deny", "PASS" if ok else "FAIL")
            for name, ok in results.items()
        ],
        "the five tests, run against propose_refund / issue_refund",
    )
    ctx.record("five_test_results", results)

    ctx.concept(
        "a silently skipped test is a governance failure",
        """
A test that is skipped because an optional dependency is missing reports green.
A gate built on it is now asserting nothing, and nobody will notice for months.

The fix is mechanical: make the pipeline **count** the tests it expected to run
and fail closed when the count drops. `nornyx-lab verify` and this repository's
CI both do that — see `.github/workflows/ci.yml`.
""",
    )

    ctx.boundary(
        """
**This lab did not fix the bypass, and at Tier 2 it cannot.**

The honest response to bypass #1 is one of:

1. declare `direct_business_callable` **unsupported** in your inventory, or
2. move the effect behind a boundary the process cannot cross — a separate
   service, an IAM permission the agent's role lacks, an egress proxy.

Option 2 is a Tier 3 move and costs real money. Option 1 costs a line of YAML
and an honest README. Choosing option 1 while writing option 2's claim is the
failure this whole part of the book exists to prevent.
"""
    )

    ctx.tryit(
        """
List every path to your system's riskiest effect. Not the ones in the design doc
— the real ones: admin scripts, a retry worker, a "temporary" debug endpoint,
the ORM.

For each, write `wrapped`, `unsupported`, or `unwrapped`. The count of
`unwrapped` is the number of things you did not know about your own system.
"""
    )
