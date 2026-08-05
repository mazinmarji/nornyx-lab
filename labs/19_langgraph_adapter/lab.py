"""Lab 19 — LangGraph: occurrence identity under retries and loops.

A second framework, the same decision engine, and a much harder evidence problem:
graphs loop, retry, branch, interrupt, and resume.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from nornyx.agentic import EvaluationContext, EvidenceRecorder

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.engine import LabContext
from nornyx_lab.optional import try_import

MISSION = "mission.graph"


class GraphState(TypedDict):
    log: Annotated[list, operator.add]


def run(ctx: LabContext) -> None:
    ctx.section("What a governance integration needs from a graph framework")

    ctx.say(
        """
LangGraph runs a **state graph**: nodes transform state, edges route between
them, a checkpointer persists progress, and each node execution carries
framework-supplied metadata.

That last item is the only reason this integration is possible. A governed node
must answer *which execution of this node is this?* — and it must answer from
information the framework already publishes, never by inventing an id of its
own. An adapter that generated its own occurrence ids would produce evidence
that could not be correlated with the framework's own view of what ran.
"""
    )

    adapter = try_import("nornyx_agentic_adapters.langgraph", extra="langgraph")
    graph_mod = try_import("langgraph.graph", extra="langgraph")
    if adapter is None or graph_mod is None:
        ctx.boundary(
            "**LangGraph is not installed, so this lab cannot run its live section.**\n\n"
            "```bash\nuv pip install -e '.[langgraph]'\n```\n\n"
            "A named skip, not a silent one."
        )
        return

    from langgraph.graph import END, START, StateGraph
    from nornyx_agentic_adapters import SurfaceBinding
    from nornyx_agentic_adapters.errors import AdapterDenied

    az = authorizer_for(shared_contract("ledger"))
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )
    recorder = EvidenceRecorder.for_occurrences(az, eval_ctx, producer_id="nornyx-lab.langgraph")
    ledger = ctx.ledger("governed graph")

    def governed(identity: str, capability: str, action):
        return adapter.make_governed_node(
            binding=SurfaceBinding(
                surface="node_invocation", identity_ref=identity, capability_ref=capability
            ),
            authorizer=az,
            context=eval_ctx,
            recorder=recorder,
            mission_id=MISSION,
            action=action,
        )

    # ------------------------------------------------------------ the graph
    ctx.section("A three-node graph where node two is not authorized")

    ctx.code(
        """graph = StateGraph(GraphState)
graph.add_node("read",   governed("identity.intake_agent", "read_customer_case", read_case))
graph.add_node("refund", governed("identity.intake_agent", "issue_refund",       do_refund))
graph.add_edge(START, "read"); graph.add_edge("read", "refund"); graph.add_edge("refund", END)
app = graph.compile()""",
        caption="the intake agent may read a case; it may not move money",
    )

    graph = StateGraph(GraphState)
    graph.add_node(
        "read",
        governed(
            "identity.intake_agent",
            "read_customer_case",
            lambda state: {"log": [northstar.read_case(ledger, "CASE-1041")["case_id"]]},
        ),
    )
    graph.add_node(
        "refund",
        governed(
            "identity.intake_agent",
            "issue_refund",
            lambda state: {"log": [northstar.issue_refund(ledger, 5000.0)]},
        ),
    )
    graph.add_edge(START, "read")
    graph.add_edge("read", "refund")
    graph.add_edge("refund", END)
    app = graph.compile()

    denied_at = None
    try:
        app.invoke({"log": []})
    except AdapterDenied as exc:
        denied_at = str(exc).split(":")[0]

    ctx.decisions(
        [
            ("node 'read' (capability held)", "allow", "ALLOWED"),
            ("node 'refund' (capability not held)", "deny", denied_at or "ALLOWED"),
        ],
        "one real Graph.invoke()",
    )

    ungoverned = ctx.ledger("plain graph")
    northstar.read_case(ungoverned, "CASE-1041")
    northstar.issue_refund(ungoverned, 5000.0)

    ctx.compare(ungoverned, ledger, actions=["read_case", "issue_refund"])
    ctx.record("graph_refunds", ledger.completions("issue_refund"))
    ctx.record("denied_code", denied_at)

    ctx.verdict(
        ledger.completions("issue_refund") == 0,
        "The graph halted at the unauthorized node. The refund callable was never "
        "entered — the denial stopped the traversal, it did not clean up after it.",
    )

    # -------------------------------------------------------- occurrence id
    ctx.section("Where occurrence identity comes from")

    events = recorder.stream()["events"]
    sample = next((e for e in events if "occurrence" in e), None)
    if sample:
        ctx.code(
            "\n".join(f"{k:<14} {v}" for k, v in sample["occurrence"].items()),
            "text",
            caption="derived from LangGraph's own execution metadata",
        )
        ctx.record("occurrence_operation", sample["occurrence"]["operation_id"])

    ctx.say(
        """
- **`operation_id`** — the surface being executed. Stable across loop visits, so
  "which step is this?" has a constant answer.
- **`occurrence_id`** — taken from the framework's per-task execution id. A new
  scheduled visit gets a new one; that is what separates a **loop visit** from a
  **retry**.
- **`attempt`** — the framework's retry counter, plus a validated recorder
  prefix so attempts stay contiguous within one occurrence.

None of these is invented by the adapter. If the framework stopped publishing
execution metadata, the correct behaviour would be to fail closed, not to
generate a plausible id.
"""
    )

    ctx.say(
        """
| framework behaviour | occurrence | attempt |
|---|---|---|
| node runs once | one new occurrence | 1 |
| node **retries** after failure | **same** occurrence | 2, 3, … |
| node is visited again by a **loop** | **new** occurrence | back to 1 |
| **parallel branches** | one occurrence each, independent | 1 each |
| graph is **interrupted** | occurrence stays open | attempt recorded **incomplete** |
| graph **resumes** from a checkpoint | continues the same stream | cumulative |
"""
    )

    ctx.concept(
        "an interrupt is not a failure",
        """
When a graph hits an interrupt — a human-in-the-loop pause — the attempt is
propagated as **incomplete**, not as an error.

The distinction is load-bearing. A failed attempt says *this was tried and did
not work*; an incomplete attempt says *this is still open and will resume*.
Recording an interrupt as a failure would make every human-approval pause look
like a system fault in the evidence, and would make the "no retry after success"
rule fire on a legitimate resume.
""",
    )

    report = recorder.validate()
    ctx.say(
        f"The graph's evidence validates: `status: {report['status']}`, "
        f"**{report['event_count']} events**, `{report['counts_by_type']}`"
    )
    ctx.record("evidence_status", report["status"])

    # -------------------------------------------------------------- coverage
    ctx.section("Unsupported is not the same as unwrapped")

    entries = adapter.COVERAGE_INVENTORY.entries
    ctx.decisions(
        [(e.surface, e.status.value, e.reason.split(".")[0][:60]) for e in entries],
        "the LangGraph coverage inventory",
    )
    ctx.record("lg_surfaces", len(entries))

    ctx.say(
        """
- **unsupported** — the adapter looked at this surface and decided not to cover
  it. Your obligation: cover it elsewhere, or do not use it.
- **unwrapped** — nobody assessed it. Your obligation: **find out**.

An integrator who treats these as the same thing will compensate for the first
and be surprised by the second.
"""
    )

    ctx.boundary(
        """
**Cumulative resumed evidence establishes less than it appears to.**

A resumed stream shows you the whole history including the pause. It does not
establish that the process which resumed is the same process, on the same host,
under the same operator — only that a producer with the same declared identity
continued a stream it could validate.

At Tier 2 that is the ceiling: the producer asserts continuity, and the core
checks that the assertion is well-formed and correctly bound.
"""
    )

    ctx.tryit(
        """
1. Add a conditional edge that routes `read → read` once before continuing.
   Re-run and look at the occurrences: do you get two occurrence ids, or one
   occurrence with two attempts? Which one *should* it be, and why?
2. Give `identity.intake_agent` the `issue_refund` capability in the contract,
   rebuild, and re-run. Does the graph complete? What is now carrying the
   control that the denial used to carry?
"""
    )
