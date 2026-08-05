"""Lab 04 — Identity, capability, and authority.

Three words that teams use as synonyms and a policy engine cannot.
"""

from __future__ import annotations

from nornyx.agentic import (
    CapabilityRequest,
    DelegationRequest,
    EvaluationContext,
    HandoffRequest,
    IdentityResolutionError,
)

from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.engine import LabContext


def run(ctx: LabContext) -> None:
    az = authorizer_for(shared_contract("ledger"))
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )

    # ------------------------------------------------------------- identity
    ctx.section("Why a role string is not an identity")

    ctx.code(
        """# What a framework gives you:
agent = Agent(role="Remediation Specialist", goal="...", llm=model)

# What a governance decision needs to know:
#   - is this the SAME actor as the one in yesterday's evidence?
#   - is it still valid, or was it revoked at 14:02?
#   - which zone is it in, and what does it hold there?
#   - is it a human or not?
# A display string answers none of these, and two agents can share one.""",
        caption="the gap between a framework name and a governance identity",
    )

    ctx.say(
        "Nornyx closes it with **framework bindings**: an explicit, contract-declared "
        "map from a framework's own naming to a governance identity."
    )

    rows = []
    for framework, key in [
        ("crewai", "remediation_agent"),
        ("langgraph", "remediator"),
        ("contract_fixture", "case_analyst"),
    ]:
        resolved = az.resolve_identity(framework, key)
        rows.append((f"{framework}:{key}", "resolved", resolved))

    # The one nobody declared. This is a distinct failure kind — not a denial.
    try:
        az.resolve_identity("crewai", "helpful_intern")
        rows.append(("crewai:helpful_intern", "resolved", "?!"))
    except IdentityResolutionError as exc:
        rows.append(("crewai:helpful_intern", "deny", exc.code.value))
        ctx.record("unknown_identity_code", exc.code.value)

    ctx.decisions(rows, "resolve_identity(framework, agent_key)")

    ctx.concept(
        "three failure kinds, not one",
        """
An adapter can fail in three genuinely different ways, and collapsing them is
how teams misdiagnose incidents:

1. **Configuration error** — the binding is wrong or missing. Fix the wiring.
2. **Identity resolution error** — this runtime actor maps to no declared
   identity. Fail closed; do not invent one.
3. **Policy denial** — a known identity is not permitted to do this. Working
   as designed.

Only the third is governance operating normally. The first two mean you do not
know who is acting.
""",
    )

    # ----------------------------------------------------------- capability
    ctx.section("Capability, permission, authority")

    ctx.say(
        """
- A **capability** is a bounded action surface — a named thing that can be held.
- A **permission** is a rule that mentions one.
- **Authority** is the scoped, time-bounded relation actually in force *now*.

Authority is not a boolean and not global. Watch three identities against the
same capability:
"""
    )

    rows = []
    for identity in [
        "identity.intake_agent",
        "identity.case_analyst",
        "identity.remediation_agent",
    ]:
        for capability in ["read_customer_case", "propose_refund", "issue_refund"]:
            d = az.evaluate(CapabilityRequest(identity, capability), context=eval_ctx)
            rows.append((f"{identity.split('.')[1]} → {capability}", d.effect.value, d.code.value))
    ctx.decisions(rows, "the same three capabilities, three holders")

    ctx.say(
        "`issue_refund` is held by exactly one identity. The analyst that *proposes* "
        "a refund cannot *issue* one — that is a second capability, not a stronger "
        "version of the first."
    )

    ctx.concept(
        "the request type is part of the question",
        """
`CapabilityRequest` asks one narrow thing: **does this identity hold this
capability right now**, through membership or a valid delegation? An `ALLOW`
means "yes, it holds it" — not "go ahead".

The gates and approvals attached to `issue_refund` are evaluated when the action
crosses a boundary, through `ZoneCrossingRequest`. Watch the same identity, the
same capability, and two different questions:
""",
    )

    from nornyx.agentic import ZoneCrossingRequest

    holder = "identity.remediation_agent"
    holds = az.evaluate(CapabilityRequest(holder, "issue_refund"), context=eval_ctx)
    crossing = az.evaluate(
        ZoneCrossingRequest(holder, "zone.remediation_internal", "zone.customer_channel"),
        context=eval_ctx,
    )
    ctx.decisions(
        [
            ("does remediation_agent HOLD issue_refund?", holds.effect.value, holds.code.value),
            ("may it CROSS to the customer channel?", crossing.effect.value, crossing.code.value),
        ],
        "one identity, one capability, two questions",
    )
    ctx.record("holds_code", holds.code.value)
    ctx.record("crossing_code", crossing.code.value)
    ctx.say(
        "Holding a capability and being authorized to exercise it across a boundary "
        "are different facts, and they are asked with different request types. "
        "An adapter that only ever asks the first question has wired up half a gate."
    )

    unknown = az.evaluate(
        CapabilityRequest("identity.case_analyst", "wire_transfer"), context=eval_ctx
    )
    ctx.decisions(
        [("case_analyst → wire_transfer (undeclared)", unknown.effect.value, unknown.code.value)],
        "default-deny on an action nobody declared",
    )
    ctx.record("undeclared_code", unknown.code.value)

    ctx.concept(
        "ambient authority",
        """
The hazard the capability model exists to remove. Ambient authority is power an
actor has **by virtue of where it is running** rather than by holding something:
the process can reach the payments API, so anything in the process can spend.

An object-capability discipline replaces "I am allowed because of who I am" with
"I can act because I hold *this* bounded thing". `issue_refund` above is not a
permission Atlas could argue for — it is a capability it simply does not hold.
""",
    )

    # ------------------------------------------------- delegation vs handoff
    ctx.section("Delegation is not handoff")

    ctx.say(
        """
| | delegation | handoff |
|---|---|---|
| what moves | a bounded capability, temporarily | responsibility for a mission |
| who stays accountable | **the delegator** | the receiver, from now on |
| bounded by | capability, scope, expiry, **depth** | mission, capabilities required, expiry |
| the defect if confused | authority escalation: a "handoff" that quietly grants everything the sender held, permanently, with no depth limit | orphaned accountability |
"""
    )

    delegation = az.evaluate(DelegationRequest("delegation.refund_proposal"), context=eval_ctx)
    handoff = az.evaluate(HandoffRequest("handoff.compliance_closure"), context=eval_ctx)
    ctx.decisions(
        [
            (
                "delegation.refund_proposal (analyst → remediation)",
                delegation.effect.value,
                delegation.code.value,
            ),
            (
                "handoff.compliance_closure (intake → compliance)",
                handoff.effect.value,
                handoff.code.value,
            ),
        ],
        "both are declared, typed, and independently evaluated",
    )
    ctx.record("delegation_code", delegation.code.value)
    ctx.record("handoff_code", handoff.code.value)

    contract_text = (shared_contract("ledger") / "network.nyx").read_text(encoding="utf-8")
    start = contract_text.index("    - id: delegation.refund_proposal")
    ctx.code(contract_text[start : start + 780], "yaml", caption="the delegation, as declared")

    ctx.say(
        "Four bounds at once — `capability_ref`, `scope_refs`, `expires_at`, "
        "`max_depth: 1` — plus `onward_delegation: denied`. That last line is what "
        "stops a two-hop chain from becoming a six-hop one nobody modelled."
    )

    ctx.concept(
        "confused deputy",
        """
A component with more authority than its caller, that acts on the caller's
instructions without re-checking whose authority applies. The classic agentic
shape: a "tool executor" service holding broad credentials, invoked by an agent
that holds almost none.

The design property that removes it: the executor must act **under the caller's
capability**, not its own. In contract terms — the decision is evaluated against
`identity.case_analyst`, never against the process that happens to run the tool.
""",
    )

    ctx.boundary(
        """
`resolve_identity` maps a **claimed** framework name to a declared identity. It
does not authenticate anything. If your adapter passes `agent_key="ceo_agent"`,
Nornyx will resolve it and evaluate it as that identity.

Binding a runtime actor to a claim is the *platform's* job — process identity,
workload identity, mTLS. Nornyx states the mapping; something else must prove
the claim. Getting this backwards is the most consequential misreading of the
whole SPI.
"""
    )

    ctx.tryit(
        """
1. In `contracts/ledger/network.nyx`, add `crewai:auditor` as a framework binding
   on `identity.compliance_officer`. Rebuild with
   `python scripts/build_contracts.py ledger`, re-run, and watch it resolve.
2. Now try to give `identity.intake_agent` the `issue_refund` capability by
   editing `capability_refs`. Rebuild. What does the *membership* block do to
   your change, and why is holding it in two places not redundant?
"""
    )
