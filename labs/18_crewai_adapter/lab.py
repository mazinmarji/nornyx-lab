"""Lab 18 — The adapter boundary, and CrewAI end to end.

The first lab where something is genuinely intercepted.
"""

from __future__ import annotations

from nornyx.agentic import EvaluationContext, EvidenceRecorder

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.engine import LabContext
from nornyx_lab.optional import try_import

MISSION = "mission.remediation"


def run(ctx: LabContext) -> None:
    ctx.section("Who owns what in one governed call")

    ctx.say(
        """
| responsibility | owner | the failure if you misassign it |
|---|---|---|
| normalise the framework's arguments | **adapter** | the core grows framework-specific code and rots |
| map a framework name to an identity | **adapter** | the core has to know what "crewai" is |
| decide | **core** | two components interpret policy differently (Lab 16) |
| construct and bind evidence | **core** | the adapter can mint whatever it likes |
| execute the tool | **runtime** | the governance layer becomes an execution engine |
| report what happened | **adapter** | nobody observes the effect |

The adapter is deliberately thin. It refuses to interpret policy, and the core
refuses to touch a framework. That line is what lets CrewAI and LangGraph share
one decision engine.
"""
    )

    ctx.concept(
        "three failure kinds an adapter must keep apart",
        """
1. **Configuration error** — the binding names a capability that does not exist.
   Your wiring is wrong; nothing was decided.
2. **Identity resolution error** — this runtime actor maps to no declared
   identity. Fail closed; do not invent one.
3. **Policy denial** — a known identity may not do this. Governance working.

Only the third is normal operation. A wrapper that reports all three as "denied"
sends you hunting for a policy bug when you have a typo.
""",
    )

    adapter = try_import("nornyx_agentic_adapters.crewai_adapter", extra="crewai")
    if adapter is None:
        ctx.boundary(
            "**CrewAI is not installed, so this lab cannot run its live section.**\n\n"
            "```bash\nuv pip install -e '.[crewai]'\n```\n\n"
            "This is a real skip, not a silent one — Lab 13 explains why that "
            "distinction matters. Labs 00–17 and 20–24 do not need it."
        )
        return

    from nornyx_agentic_adapters import SurfaceBinding
    from nornyx_agentic_adapters.errors import AdapterDenied

    az = authorizer_for(shared_contract("ledger"))
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )
    recorder = EvidenceRecorder(az, eval_ctx, producer_id="nornyx-lab.crewai")

    # ------------------------------------------------------------ the wiring
    ctx.section("Build one governed tool")

    ctx.code(
        """binding = SurfaceBinding(
    surface       = "tool_invocation",          # WHICH surface this covers
    identity_ref  = "identity.case_analyst",    # WHO is acting
    capability_ref= "read_customer_case",       # WHAT they are exercising
)

tool = make_governed_tool(
    name="read_case", description="Read a sanitized customer case.",
    binding    = binding,
    authorizer = authorizer,     # injected, not re-derived  <- Lab 16
    context    = context,        # injected
    recorder   = recorder,       # injected
    mission_id = "mission.remediation",
    action     = lambda **kw: northstar.read_case(ledger, "CASE-1041"),
)""",
        caption="the whole integration",
    )

    ctx.say(
        "The three injected objects are the point. If the adapter built its own "
        "authorizer, you would have Chapter 19's split brain by construction."
    )

    # ------------------------------------------------------------- allow/deny
    ctx.section("An allowed call and a denied one")

    governed = ctx.ledger("governed tool")
    rows = []

    def build(identity: str, capability: str, action_name: str):
        return adapter.make_governed_tool(
            name=f"tool_{capability}",
            description=f"Business tool for {capability}.",
            binding=SurfaceBinding(
                surface="tool_invocation", identity_ref=identity, capability_ref=capability
            ),
            authorizer=az,
            context=eval_ctx,
            recorder=recorder,
            mission_id=MISSION,
            action=lambda **kw: northstar.perform(governed, action_name, **kw),
        )

    for label, identity, capability, action_name in [
        ("analyst reads a case", "identity.case_analyst", "read_customer_case", "read_case"),
        ("analyst issues a refund", "identity.case_analyst", "issue_refund", "issue_refund"),
        (
            "remediation agent reads a case",
            "identity.remediation_agent",
            "read_customer_case",
            "read_case",
        ),
    ]:
        tool = build(identity, capability, action_name)
        try:
            tool.run()
            rows.append((label, "allow", "ALLOWED"))
        except AdapterDenied as exc:
            rows.append((label, "deny", str(exc).split(":")[0]))

    ctx.decisions(rows, "real CrewAI BaseTool invocations")

    ungoverned = ctx.ledger("plain tool")
    northstar.read_case(ungoverned, "CASE-1041")
    northstar.issue_refund(ungoverned, 5000.0)
    northstar.read_case(ungoverned, "CASE-1041")

    ctx.compare(ungoverned, governed, actions=["read_case", "issue_refund"])
    ctx.record("governed_refunds", governed.completions("issue_refund"))
    ctx.record("ungoverned_refunds", ungoverned.completions("issue_refund"))

    report = recorder.validate()
    ctx.say(
        f"Evidence: `status: {report['status']}`, **{report['event_count']} events** — "
        f"`{report['counts_by_type']}`"
    )
    ctx.record("evidence_status", report["status"])

    ctx.verdict(
        governed.completions("issue_refund") == 0 and governed.completions("read_case") == 2,
        "Denied work has zero attempts and zero completions. Allowed work ran. "
        "The refusal is a denial, not a caught exception after the fact.",
    )

    # ------------------------------------------------------------- sequence
    ctx.section("The protected execution sequence")

    ctx.say(
        """
The shared `enforce` routine discharges a fixed ordering:

1. resolve and validate the binding — *configuration* errors surface here
2. evaluate the request against the injected authorizer
3. **record the decision** — before anything runs
4. if denied: raise `AdapterDenied`. The action is never called.
5. if allowed: call the action **exactly once**
6. record the post-action observation

Step 3 before step 5 is what makes "was the decision recorded first?" checkable
rather than a matter of trust.

And the honest limit on step 5: **exactly-once is local to this call.** It means
the wrapper does not invoke your callable twice. It is not a distributed
transaction, it does not survive a process crash between 5 and 6, and it says
nothing about retries the framework performs above the wrapper.
"""
    )

    # ------------------------------------------------------------- coverage
    ctx.section("What this integration does not cover")

    from nornyx_agentic_adapters import SurfaceStatus

    entries = adapter.COVERAGE_INVENTORY.entries
    ctx.decisions(
        [(e.surface, e.status.value, e.reason.split(".")[0][:64]) for e in entries],
        "the adapter's own published inventory",
    )
    wrapped = [e for e in entries if e.status is SurfaceStatus.WRAPPED]
    ctx.record("wrapped_count", len(wrapped))
    ctx.record("surface_count", len(entries))

    ctx.say(
        f"**{len(wrapped)} of {len(entries)} declared surfaces are wrapped.** The "
        "asynchronous tool path is `unsupported`: the adapter overrides `_run` and "
        "not `_arun`, so an async call reaches the *ungoverned* base implementation."
    )

    ctx.say(
        f"""
The version pin is part of this. `{adapter.METADATA.framework_name}` is pinned to
`{adapter.METADATA.framework_version_range}` and the adapter **fails closed at
import** on anything else — because the coverage inventory above is a statement
about the surfaces that existed in that exact version. An upgrade is a
governance event with its own evidence, not a dependency bump.
"""
    )

    ctx.boundary(
        """
**"CrewAI is governed" is false.** The defensible replacement:

> On the **synchronous `BaseTool._run` surface** of `crewai==1.15.4`, a tool
> built by `make_governed_tool` evaluates a declared capability against a
> lock-verified contract before invoking its business callable, records the
> decision before execution, and raises `AdapterDenied` without invoking it when
> denied. **Five of six declared surfaces are not covered**, including the async
> tool path. Direct invocation of the underlying callable is not covered by
> anything. This is Tier 2: cooperative, in-process, self-reported.

Longer. True. Notice how much of it is about what is *not* covered.
"""
    )

    ctx.tryit(
        """
1. Build a governed tool whose `capability_ref` does not exist in the contract.
   Which of the three failure kinds do you get, and how is it different from a
   denial?
2. Call `northstar.issue_refund(ledger, 5000.0)` directly, in the same process,
   right after a denied tool call. Count the completions. Which row of the
   coverage inventory should have warned you?
"""
    )
