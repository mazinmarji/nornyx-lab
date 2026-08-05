"""Lab 03 — The vocabulary.

Six terms that get used interchangeably in vendor material and mean genuinely
different things. Each one is demonstrated rather than defined.
"""

from __future__ import annotations

from nornyx.agentic import CapabilityRequest, EvaluationContext

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.engine import LabContext

IDENTITY = "identity.case_analyst"


def run(ctx: LabContext) -> None:
    az = authorizer_for(shared_contract("ledger"))
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )

    # ------------------------------------------------------------- PDP / PEP
    ctx.section("Decision point vs enforcement point")

    ctx.concept(
        "PDP and PEP",
        """
- A **policy decision point (PDP)** answers *may this happen?* It computes.
- A **policy enforcement point (PEP)** sits on the path from intent to effect
  and *applies* that answer. It blocks.

The separation is architectural, not cosmetic. A PDP can be perfect and change
nothing, because the constraint comes from the PEP's **position**, not from the
decision's correctness. Chapter 10: a correct decision does not constrain an
action whose path to its effect never traverses an element that applies it.
""",
    )

    # The SAME decision, three wirings.
    # The CaseAnalyst may PROPOSE a refund. It may not issue one — that is a
    # different capability, held by a different identity.
    decision = az.evaluate(CapabilityRequest(IDENTITY, "issue_refund"), context=eval_ctx)
    ctx.decisions(
        [("CaseAnalyst asks to issue a refund", decision.effect.value, decision.code.value)],
        "one decision from the PDP",
    )

    # (a) PDP only — the answer is computed and discarded.
    pdp_only = ctx.ledger("PDP, no PEP")
    pdp_only.decision(decision.code.value, decision.effect.value)
    northstar.issue_refund(pdp_only, 5000.0)  # nothing consults `decision`

    # (b) PDP + PEP — the answer gates the call.
    enforced = ctx.ledger("PDP + PEP")
    enforced.decision(decision.code.value, decision.effect.value)
    if decision.allowed:
        northstar.issue_refund(enforced, 5000.0)

    # (c) PEP present but bypassed — the effect is reachable another way.
    bypassed = ctx.ledger("PEP bypassed")
    bypassed.decision(decision.code.value, decision.effect.value)
    northstar.issue_refund(bypassed, 5000.0)  # a second code path, unwrapped

    ctx.code(
        """# (a) decision computed, never applied
decision = pdp.evaluate(request)          # correct answer
issue_refund(ledger, 5000.0)              # ... and ignored

# (b) decision applied at the only path to the effect
if pdp.evaluate(request).allowed:         # PEP
    issue_refund(ledger, 5000.0)

# (c) the PEP exists, but so does another route to the same effect
if pdp.evaluate(request).allowed:
    issue_refund(ledger, 5000.0)
admin_tools.force_refund(5000.0)          # <- the one nobody wrapped
""",
        caption="three wirings, one decision",
    )

    ctx.compare(pdp_only, enforced, actions=["issue_refund"])
    ctx.record("pdp_only_completions", pdp_only.completions("issue_refund"))
    ctx.record("enforced_completions", enforced.completions("issue_refund"))
    ctx.record("bypassed_completions", bypassed.completions("issue_refund"))

    ctx.verdict(
        enforced.completions("issue_refund") == 0,
        "Same decision, opposite outcomes. Where the check sits decides whether "
        "it is governance or commentary.",
    )

    # ---------------------------------------------------------- design/runtime
    ctx.section("Design-time vs runtime governance")

    ctx.say(
        """
| | design-time | runtime |
|---|---|---|
| **runs when** | you author and merge a contract | an agent is about to act |
| **asks** | is this policy coherent, complete, reviewed? | may *this* actor do *this* now? |
| **fails as** | a red build | a denied action |
| **in this repo** | `nornyx check`, `generate`, `lock`, the CI gates | `Authorizer.evaluate` through an adapter |
| **cannot** | stop anything at run time | tell you the policy was reviewed |

A complete discipline needs both, and neither substitutes for the other. Labs
01 and 14–15 are design-time; labs 09 and 16–19 are runtime.
"""
    )

    # ------------------------------------------------------ evidence/assurance
    ctx.section("Evidence vs assurance, cooperative vs independent")

    ctx.concept(
        "who is trusted, and to do what",
        """
**Evidence** is a record bound to a subject. **Assurance** is a claim about how
much that record can bear — and it depends entirely on who produced it and
whether they could have lied.

- **Cooperative enforcement**: the enforcing component runs *inside* the process
  it governs, and depends on that process calling it. It can be bypassed by code
  in the same process. Nornyx's SPI and the framework adapters are cooperative.
- **Independent enforcement**: the control sits outside the agent's process, on
  a path the agent cannot avoid — an egress proxy, a sandbox, an IAM boundary.
  It cannot be talked out of it.

Chapter 26 is blunt about the consequence: independent enforcement requires four
properties at once, and having three of them is not a partial version of the
fourth.
""",
    )

    ctx.say(
        "The authorizer will tell you its own boundary if you ask it. Here is what "
        "it is willing to assert about itself:"
    )
    from nornyx.agentic import SPI_VERSION

    ctx.code(
        f"""nornyx.agentic SPI version : {SPI_VERSION}
subject_revision bound     : {az.subject_revision}
enforcement model          : cooperative (Tier 2)

It does NOT:
  authenticate the agent      -> identity is asserted by the adapter, not proven
  authenticate the approver   -> the approval record is supplied, not verified
  execute the tool            -> your application does that
  attest that an event is true-> it validates SHAPE and BINDING, not reality
""",
        "text",
        caption="the honest interface",
    )

    # ---------------------------------------------------------- positioning
    ctx.section("Where this sits among things you already run")

    ctx.say(
        """
| family | the question it answers | what it does not answer |
|---|---|---|
| IAM / identity providers | who is this principal? | may this *agent* take this *action* now? |
| API gateways, egress proxies | may this request leave? | was it authorized under a reviewed policy? |
| Service meshes | may service A talk to service B? | may this capability be exercised? |
| Policy engines (OPA, Cedar) | is this request permitted? | who reviewed the policy, and against what evidence? |
| Observability / SIEM | what happened? | was it allowed to happen? |
| Guardrail services | is this text unsafe? | is this *action* authorized? |
| Secret managers | may this process read this secret? | may this agent use the tool at all? |

None of these is a competitor and none is a substitute. A governed agentic
system is the layer that names the actor, bounds the action, and binds the
evidence — and then hands enforcement to whichever of the above sits on the
path.
"""
    )

    ctx.boundary(
        """
**The trap this vocabulary exists to prevent.** "We use OPA, so our agents are
governed." OPA is an excellent PDP. Whether your agents are governed depends on
where its answers are applied and whether every path to the effect goes through
that point — which is a question about your architecture, not about OPA.
"""
    )

    ctx.tryit(
        """
Draw your own system's path from *agent intends X* to *X has happened*. Mark
every element on that path. Now mark which one applies a decision.

If the answer is "none", you have a PDP and no PEP — the (a) case above. If the
answer is "one, but there are three paths", you have Lab 13's problem.
"""
    )
