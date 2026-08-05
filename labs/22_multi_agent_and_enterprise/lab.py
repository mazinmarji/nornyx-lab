"""Lab 22 — Dev agents, multi-agent networks, hierarchies, and operations.

Four chapters that share one question: what happens when there is more than one
agent, more than one owner, and something goes wrong at 3am?
"""

from __future__ import annotations

from nornyx.agentic import (
    ApprovalAssertion,
    CapabilityRequest,
    DelegationRequest,
    EvaluationContext,
    EvidenceRecorder,
    HandoffRequest,
    ZoneCrossingRequest,
)

from nornyx_lab import northstar
from nornyx_lab.constants import (
    APPROVAL_EXPIRES_AT,
    APPROVAL_ISSUED_AT,
    LAB_AS_OF,
    LAB_SUBJECT_REVISION,
)
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.engine import LabContext

LEDGER = shared_contract("ledger")


def run(ctx: LabContext) -> None:
    az = authorizer_for(LEDGER)
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )

    # ------------------------------------------------------------ Forge
    ctx.section("Forge — governing a software-development agent")

    ctx.say(
        """
Northstar's coding agent opens pull requests. Where does the approval boundary
sit? Not "on risky changes" — that is a judgement nobody can encode. On
**action classes**:

| action | decision | approver | why here |
|---|---|---|---|
| read the repository | freely allowed | — | no effect |
| author a patch on a branch | freely allowed | — | reversible, reviewable |
| run tests | freely allowed | — | no external effect |
| **merge to main** | human approval | a human who did **not** direct the agent | irreversible, ships |
| **publish a release** | human approval + evidence | release owner | irreversible, external |

The boundary sits where **reversibility** ends, not where risk feels high.
"""
    )

    ctx.concept(
        "directing an agent counts as making",
        """
Maker–checker requires the maker and the checker to be different **authorities**.
When an engineer prompts an agent to open a change, that engineer is the maker —
the agent is an instrument, not an independent party.

So the approver must be a third human. A system that lets the prompting engineer
approve the agent's PR has maker–checker in the diagram and one authority in
reality. This is why the constraint is expressed over **identities and
capabilities** rather than over roles or processes: two processes can run under
one authority, and one process can act for two.
""",
    )

    # ------------------------------------------------------ multi-agent
    ctx.section("Ledger — a multi-agent workflow as typed declarations")

    ctx.say(
        "Four agents, one refund. Every relationship below is a **declaration** "
        "with a validity interval — not a convention expressed in Python."
    )

    rows = []
    for label, request in [
        (
            "intake → read_customer_case",
            CapabilityRequest("identity.intake_agent", "read_customer_case"),
        ),
        ("analyst → propose_refund", CapabilityRequest("identity.case_analyst", "propose_refund")),
        ("analyst → issue_refund", CapabilityRequest("identity.case_analyst", "issue_refund")),
        (
            "remediation → issue_refund",
            CapabilityRequest("identity.remediation_agent", "issue_refund"),
        ),
        ("delegation: analyst ⇒ remediation", DelegationRequest("delegation.refund_proposal")),
        ("handoff: intake ⇒ compliance", HandoffRequest("handoff.compliance_closure")),
        (
            "compliance → request_human_approval",
            CapabilityRequest("identity.compliance_officer", "request_human_approval"),
        ),
    ]:
        d = az.evaluate(request, context=eval_ctx)
        rows.append((label, d.effect.value, d.code.value))
    ctx.decisions(rows, "the network, evaluated")

    ctx.say(
        """
Read the shape: **no single identity can complete a refund alone.**

- the analyst may *propose* but not *issue*
- the remediation agent may *issue* but only across a gate that demands approval
- the compliance officer may *request* approval but `can_approve: false`
- the approver is a **human role**, and no agent holds it

That is separation of duties expressed over identities and capabilities. It
survives someone adding a fifth agent, because the constraint is not "these two
processes are different".
"""
    )

    # --------------------------------------------------- consequence tiers
    ctx.section("Escalation by consequence, and the part a declaration cannot decide")

    ctx.say(
        """
| consequence band | decision | who |
|---|---|---|
| reversible, bounded | allowed, recorded | nobody |
| irreversible, small | one human approval | the owning team |
| irreversible, large | approval + independent review | risk owner |
| systemic | approval + review + a named executive | governance owner |

A declaration layer can decide **which band an action is in** and **that an
approval of that band is required**. It cannot decide **whether this particular
approval was wise**. That judgement is what the human is for — and pretending
the layer supplies it is the tier inflation of Lab 12 in organizational form.
"""
    )

    approval = ApprovalAssertion(
        approval_ref="agentic_network_authority",
        claimed_approver_ref="human.network_governance_owner",
        claimed_actor_type="human",
        role="network_governance_owner",
        granted=True,
        action_ref="notify_customer",
        subject_revision=LAB_SUBJECT_REVISION,
        issued_at=APPROVAL_ISSUED_AT,
        expires_at=APPROVAL_EXPIRES_AT,
        evidence_refs=("approval_record", "agentic_network_contract_review"),
    )
    crossing = az.evaluate(
        ZoneCrossingRequest(
            "identity.remediation_agent",
            "zone.remediation_internal",
            "zone.customer_channel",
            approval,
        ),
        context=eval_ctx,
    )
    without = az.evaluate(
        ZoneCrossingRequest(
            "identity.remediation_agent",
            "zone.remediation_internal",
            "zone.customer_channel",
        ),
        context=eval_ctx,
    )
    ctx.decisions(
        [
            ("notify the customer, no approval", without.effect.value, without.code.value),
            ("notify the customer, human approval", crossing.effect.value, crossing.code.value),
        ],
        "the escalation, exercised",
    )
    ctx.record("escalation_without", without.code.value)
    ctx.record("escalation_with", crossing.code.value)

    # ----------------------------------------------------- the hierarchy
    ctx.section("The five-level policy stack")

    ctx.say(
        """
| level | owner | cadence | artifact |
|---|---|---|---|
| 1 regulatory / statutory | legal | years | interpreted obligations |
| 2 enterprise policy | risk | quarters | canonical policy documents |
| 3 domain / division | platform | months | a domain profile |
| 4 application | product team | weeks | a `.nyx` contract |
| 5 environment | operations | days | deployment config |

**A lower layer may narrow but never silently widen.** You proved that
mechanically in Lab 07. Organizationally it means level 4 cannot loosen level 2,
and a necessary weakening becomes a bounded, owned, expiring **exception**
attached to level 2 — visible on a report rather than buried in a diff.

Nornyx implements composition (levels 3–4) and cross-repository policy
comparison. It does **not** implement a full hierarchy engine: conflict
semantics across administrative domains, weakening reports, and exception
registries are Chapter 32's "would additionally require" list, and the project
has ruled some of them out on purpose.
"""
    )

    # -------------------------------------------------------- operations
    ctx.section("3am — reconstructing an incident")

    recorder = EvidenceRecorder(az, eval_ctx, producer_id="nornyx-lab.ops")
    mission = "mission.incident-4471"
    ledger = ctx.ledger("incident")

    d1 = az.evaluate(
        CapabilityRequest("identity.intake_agent", "read_customer_case"), context=eval_ctx
    )
    recorder.record_decision(d1, mission_id=mission)
    if d1.allowed:
        northstar.read_case(ledger, "CASE-1041")
        recorder.record_observation(
            "tool_invoked",
            mission_id=mission,
            actor_ref="identity.intake_agent",
            capability_ref="read_customer_case",
        )
    d2 = az.evaluate(CapabilityRequest("identity.intake_agent", "issue_refund"), context=eval_ctx)
    recorder.record_decision(d2, mission_id=mission)

    report = recorder.validate()
    ctx.say("The seven-step reconstruction chain, walked on this run:")
    ctx.code(
        f"""1. contract      {LEDGER.name}/network.nyx
2. composition   profile agentic_network + 3 modules      (governance explain)
3. lock          {report["network_lock_digest"][:26]}…
4. approval      agentic_network_authority, human, {APPROVAL_ISSUED_AT}
5. events        {report["event_count"]} records, status={report["status"]}
6. artifacts     10 generated control artifacts, lock-verified
7. interpretation ... this is where it stops""",
        "text",
        caption="contract → composition → lock → approval → events → artifacts → interpretation",
    )
    ctx.record("reconstruction_events", report["event_count"])
    ctx.record("reconstruction_status", report["status"])

    ctx.say(
        """
**Operational signals worth paging on**, and the ones that are not:

| signal | route |
|---|---|
| lock-check failure in the merge lane | **page** — the control is broken |
| drift-gate failure | block the build; do not page |
| denial *rate* spike on one capability | investigate — either an attack or a bad policy |
| approval latency climbing | a capacity problem, not a security one |
| approval *fatigue* (approvals granted in under N seconds) | investigate — the attestation is becoming a reflex |
| a single denial | **nothing.** That is the system working. |

Paging on single denials is how teams learn to ignore the governance channel.
"""
    )

    ctx.boundary(
        """
**Where reconstruction stops.** Step 7 is interpretation, and it is human.

You can prove *which contract was in force*, *what was decided*, *what evidence
was bound*, and *who the approval names*. You cannot prove from these artifacts
that the named human actually reviewed anything, or that the events describe
reality — those are the Tier 2 ceiling from Lab 12, restated at 3am when it
matters.

And the multi-agent bypass argument, in one line: with five agents in one
process, any one of them can call a business callable directly. The more agents
share a trust domain, the stronger the case for moving the effect behind an
**independent** boundary.
"""
    )

    ctx.tryit(
        """
1. Revoke `identity.remediation_agent`'s membership by setting its `status` to
   `revoked` in `contracts/ledger/network.nyx`, rebuild, and re-run. Which
   decisions change, and which stay the same? Why does the delegation still
   evaluate?
2. Write the merge gate for Forge as a contract: identities, capabilities, the
   approval, and the zone crossing from `branch` to `main`. Then apply the
   five-test rule from Lab 13 to it.
"""
    )
