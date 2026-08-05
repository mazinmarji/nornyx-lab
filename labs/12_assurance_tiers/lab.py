"""Lab 12 — Assurance tiers: what you are allowed to claim.

Everything you built in labs 00–11 works. This lab is about what sentence you
may write down afterwards without lying.
"""

from __future__ import annotations

from nornyx.agentic import CapabilityRequest, EvaluationContext, EvidenceRecorder

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.engine import LabContext

ID = "identity.research_assistant"


def run(ctx: LabContext) -> None:
    ctx.section("Three tiers")

    ctx.say(
        """
| tier | the property it adds | what it can survive |
|---|---|---|
| **1 — declared** | the rule exists, is versioned and reviewable | an argument about what the policy *is* |
| **2 — cooperative** | a component *in the process* evaluates and refuses, and produces bound evidence | a mistake, a confused planner, a prompt injection |
| **3 — independent** | the control sits outside the agent's reach, on a path it cannot avoid, and attests separately | an adversary **inside** the process |

Each tier adds exactly one property, and the jump from 2 to 3 is the expensive
one — because it is the only jump that changes who you are defending against.
"""
    )

    ctx.section("Where this repository sits, precisely")

    az = authorizer_for(shared_contract("atlas"))
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )
    recorder = EvidenceRecorder(az, eval_ctx, producer_id="nornyx-lab.tiers")
    decision = az.evaluate(CapabilityRequest(ID, "publish_external"), context=eval_ctx)
    recorder.record_decision(decision, mission_id="mission.tier-demo")
    report = recorder.validate()

    ctx.decisions(
        [("Atlas → publish_external", decision.effect.value, decision.code.value)],
        "a real denial, with bound evidence",
    )
    ctx.say(
        f"The evidence validates: `status: {report['status']}`, "
        f"`{report['event_count']}` events, `{len(report['diagnostics'])}` diagnostics."
    )

    ctx.say(
        """
That is a solid **Tier 2** result. It is not Tier 3, and the difference is not
effort — it is structural:

- the identity was **asserted** by the caller, not authenticated
- the evidence was **produced by the same process** that acted
- the enforcement point is **in-process** and can be bypassed by code beside it

None of those is a bug to fix. They are the definition of a cooperative
boundary. A Tier 3 claim needs a component the agent cannot reach.
"""
    )

    # --------------------------------------------------------- self-report
    ctx.section("Why the ledger caps the claim")

    honest = ctx.ledger("honest producer")
    northstar.issue_refund(honest, 5000.0)

    dishonest = ctx.ledger("dishonest producer")
    # The business function runs, but this producer simply declines to say so.
    receipt = f"refund:acct-88213:{5000.0:.2f}"  # noqa: F841 - the effect happened

    ctx.compare(dishonest, honest, actions=["issue_refund"])
    ctx.say(
        "Both runs moved the money. Only one wrote it down. The ledger is "
        "**application-produced evidence**, and an application that lies about "
        "its own side effects is not detectable *by that ledger*.\n\n"
        "That is the ceiling. No amount of careful ledger design raises it, "
        "because the ledger and the actor are the same trust domain."
    )
    ctx.record("dishonest_completions", dishonest.completions("issue_refund"))

    # ------------------------------------------------------- eight questions
    ctx.section("The eight questions, applied to one claim")

    ctx.say(
        """
Take: *"Atlas cannot publish externally without human approval."*

| # | question | answer here |
|---|---|---|
| 1 | **Which surface** does this cover? | the governed tool path, when invoked through the adapter |
| 2 | **What enforces it** — decision or compulsion? | an in-process decision applied by a wrapper |
| 3 | **Who produced the evidence**? | the adapter, in the same process as the agent |
| 4 | **What binds it** to a subject? | contract digest, lock digest, `subject_revision` |
| 5 | **What happens when the enforcer fails**? | fail-closed, if you wrote the `except` branch that way |
| 6 | **What is uncovered**? | direct calls, async paths, anything not routed through the wrapper |
| 7 | **Which adversary** is in scope? | a confused planner and injected instructions — *not* hostile in-process code |
| 8 | **What would falsify** the claim? | one completed publish with no preceding recorded decision |

Question 8 is the one that separates engineering from marketing. If you cannot
name the observation that would prove your claim false, you have not made a
claim.
"""
    )

    # ---------------------------------------------------------- inflation
    ctx.section("Tier inflation, and the rewrite")

    ctx.say(
        """
| inflated | precise | which word did the work |
|---|---|---|
| "Our agents are governed." | "The synchronous tool surface of this crew is governed at Tier 2." | *which surface* |
| "All actions are audited." | "All actions **routed through the adapter** produce bound evidence." | *routed through* |
| "Nornyx prevents unauthorized refunds." | "A refund attempted through the governed tool is denied without a valid approval." | *attempted through* |
| "We have an immutable audit trail." | "Evidence records are content-bound; immutability depends on the store." | *content-bound* vs *immutable* |
| "The system is compliant with X." | "These controls are interpretively mapped to X clauses 4.2 and 6.1." | *interpretively mapped* |

Notice the pattern: every honest rewrite names **a surface** and **a
mechanism**. Every inflated version deletes both.
"""
    )

    ctx.concept(
        "a tier applies to a surface",
        """
There is no such thing as "a Tier 2 system". Tiers attach to **a surface and an
evidence package**.

One application can legitimately be Tier 3 on payments (an IAM boundary the
process genuinely cannot cross), Tier 2 on its tool calls (a cooperative
adapter), and Tier 1 on its data exports (a policy that is written down and
nothing more). Stating one tier for the whole thing is inflation by
construction — it silently promotes the weakest surface to the strength of the
strongest.
""",
    )

    ctx.boundary(
        """
**Overclaiming is a security failure, not a communication failure.**

The harm path is concrete: a team told "the framework is governed" wires up a
second execution path, sees no reason to review it, and ships an unguarded
route to production. The inflated sentence *caused* the gap by removing the
reason to look.

This is why publishing what you do **not** cover increases security. Lab 13
makes that list machine-readable.
"""
    )

    ctx.tryit(
        """
Find a governance claim in your own README, runbook, or vendor's marketing.
Rewrite it in the eight-element form above.

If you cannot fill in row 6 — *what is uncovered* — you do not yet know the
answer, and that is the finding.
"""
    )
