"""Lab 06 — Policy semantics and deterministic evaluation.

Why three values and not two, why default-deny makes a rule set total, and the
three ordinary programming habits that quietly destroy reproducible decisions.
"""

from __future__ import annotations

from nornyx.agentic import (
    ApprovalAssertion,
    CapabilityRequest,
    DelegationRequest,
    EvaluationContext,
    ZoneCrossingRequest,
)

from nornyx_lab.constants import (
    APPROVAL_EXPIRES_AT,
    APPROVAL_ISSUED_AT,
    LAB_AS_OF,
    LAB_SUBJECT_REVISION,
)
from nornyx_lab.contract import authorizer_for, nornyx, shared_contract
from nornyx_lab.engine import LabContext

ID = "identity.research_assistant"
INTERNAL = "zone.research_internal"
PUBLIC = "zone.public_web"


def _approval(**overrides) -> ApprovalAssertion:
    base = dict(
        approval_ref="agentic_network_authority",
        claimed_approver_ref="human.network_governance_owner",
        claimed_actor_type="human",
        role="network_governance_owner",
        granted=True,
        action_ref="publish_external",
        subject_revision=LAB_SUBJECT_REVISION,
        issued_at=APPROVAL_ISSUED_AT,
        expires_at=APPROVAL_EXPIRES_AT,
        evidence_refs=("approval_record", "agentic_network_contract_review"),
    )
    base.update(overrides)
    return ApprovalAssertion(**base)


def run(ctx: LabContext) -> None:
    az = authorizer_for(shared_contract("atlas"))
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )

    # ------------------------------------------------------- the four things
    ctx.section("What a policy language must define")

    ctx.say(
        """
Omit any one of these and a policy becomes unevaluable — not merely incomplete:

| | in Nornyx |
|---|---|
| **subjects** — who acts | `agent_identities`, resolved from framework bindings |
| **actions** — what may be done | `capabilities`, each with an `actions` list |
| **conditions** — under what circumstances | zones, gates, approvals, validity intervals |
| **a decision domain** — what an answer may be | `allow` / `deny` / `approval_required` |
"""
    )

    # ------------------------------------------------------ three-valued
    ctx.section("Three values, not two")

    rows = []
    d = az.evaluate(CapabilityRequest(ID, "search_web"), context=eval_ctx)
    rows.append(("Atlas → search_web", d.effect.value, d.code.value))

    d = az.evaluate(CapabilityRequest(ID, "publish_external"), context=eval_ctx)
    rows.append(("Atlas → publish_external (not held)", d.effect.value, d.code.value))

    d = az.evaluate(ZoneCrossingRequest(ID, INTERNAL, PUBLIC), context=eval_ctx)
    rows.append(("Atlas crosses to public_web", d.effect.value, d.code.value))

    d = az.evaluate(ZoneCrossingRequest(ID, INTERNAL, PUBLIC, _approval()), context=eval_ctx)
    rows.append(("… with a valid human approval", d.effect.value, d.code.value))

    ctx.decisions(rows, "all three values, from one contract")
    ctx.record("effects_seen", sorted({r[1] for r in rows}))

    ctx.concept(
        "approval_required is not deny, and not defer",
        """
- **deny** — the answer is no. Retrying changes nothing.
- **approval_required** — the answer is *not yet*, and the missing input is
  named: a human approval bound to this action and this revision.
- **defer** (which this domain does *not* have) would mean "ask again later and
  maybe the ambient state will differ". That is precisely what a deterministic
  engine must never say.

Collapsing `approval_required` into `deny` loses the actionable part. Collapsing
it into `allow` with a warning is how organizations discover, during an audit,
that "approval" was a log line.
""",
    )

    # ------------------------------------------------------- default-deny
    ctx.section("Default-deny makes the rule set total")

    rows = []
    for capability in ["draft_briefing", "launch_missiles", "read_secrets"]:
        d = az.evaluate(CapabilityRequest(ID, capability), context=eval_ctx)
        rows.append((f"Atlas → {capability}", d.effect.value, d.code.value))
    d = az.evaluate(DelegationRequest("delegation.invented"), context=eval_ctx)
    rows.append(("undeclared delegation", d.effect.value, d.code.value))
    ctx.decisions(rows, "nothing falls through")

    ctx.say(
        "Two of those capabilities were never mentioned anywhere in the contract. "
        "The engine did not need a rule for them — **absence is the rule**. That is "
        "what makes the rule set *total*: every possible request has an answer, so "
        "evaluation order cannot change the outcome."
    )

    # -------------------------------------------------------- determinism
    ctx.section("Determinism, and the three things that destroy it")

    request = CapabilityRequest(ID, "search_web")
    outcomes = {az.evaluate(request, context=eval_ctx).code.value for _ in range(200)}
    ctx.record("distinct_outcomes", len(outcomes))
    ctx.say(
        f"The same request, evaluated **200 times**: `{len(outcomes)}` distinct "
        f"outcome(s) — `{outcomes.pop()}`."
    )

    ctx.concept(
        "the three destroyers",
        """
1. **Ambient state** — the decision reads something the request did not carry:
   an environment variable, a cache, a feature flag. Same request, different
   answer, no way to reproduce the old one.
2. **Wall-clock time** — the decision calls `now()`. Now the answer depends on
   when you asked, and last Tuesday's denial cannot be reproduced at all.
3. **Mutable retained structures** — the engine hands out a live view of its own
   state and something mutates it. Now decisions depend on evaluation history.

Nornyx closes all three by construction: every temporal question is answered
from `EvaluationContext.decision_at`, which **you** supply; the authorizer's
state is exposed only as frozen, detached views; and nothing is read from the
environment during evaluation.
""",
    )

    ctx.say("Time is an *input*, not an ambient fact. Move it and the answer moves:")
    late_ctx = EvaluationContext(
        decision_at="2026-09-01T00:00:00Z", observed_subject_revision=LAB_SUBJECT_REVISION
    )
    late = az.evaluate(ZoneCrossingRequest(ID, INTERNAL, PUBLIC, _approval()), context=late_ctx)
    on_time = az.evaluate(ZoneCrossingRequest(ID, INTERNAL, PUBLIC, _approval()), context=eval_ctx)
    ctx.decisions(
        [
            (f"crossing at {LAB_AS_OF}", on_time.effect.value, on_time.code.value),
            ("crossing at 2026-09-01 (same approval)", late.effect.value, late.code.value),
        ],
        "the only thing that changed is decision_at",
    )
    ctx.record("late_code", late.code.value)
    ctx.say(
        "Both are correct and both are reproducible **forever**, because the instant "
        "is part of the question. That is why every command in this repo passes "
        "`--as-of`."
    )

    # ------------------------------------------------------- closed schema
    ctx.section("Closed schemas as semantic hygiene")

    broken = ctx.dir / "broken.nyx"
    broken.write_text(
        (shared_contract("atlas") / "network.nyx").read_text(encoding="utf-8")
        + "\nsuper_powers:\n  - name: bypass_everything\n",
        encoding="utf-8",
    )
    result = ctx.cli(nornyx("check", str(broken), "--as-of", LAB_AS_OF), expected_fail=True)
    ctx.record("closed_schema_codes", result.codes())
    broken.unlink(missing_ok=True)

    ctx.say(
        """
Read the **severity**, not just the code. `UNKNOWN_TOP_LEVEL_BLOCK` is a
**warning**, and `nornyx check` still exits 0.

That is the honest behaviour, and it is more useful than a hard failure: the
closed schema guarantees an unrecognised block is *named, coded, and reported*,
so a typo cannot silently become an unenforced rule. **Whether that stops your
build is your pipeline's decision** — which is exactly why diagnostic codes are
a public interface (Lab 17). You gate on the code; the tool reports the fact.

What a closed schema does not buy you: any correctness at all about the blocks
that *are* recognised.
"""
    )

    ctx.say(
        """
For orientation against engines you may already run:

| | XACML | Rego (OPA) | Cedar | Nornyx |
|---|---|---|---|---|
| decision domain | permit / deny / not-applicable / indeterminate | whatever you return | allow / deny | allow / deny / approval-required |
| conflict handling | combining algorithms you choose | your code | forbid overrides permit | default-deny, monotone composition |
| language | XML | general-purpose (Turing-complete) | purpose-built, analysable | declarative, closed schema |
| human approval | model it yourself | model it yourself | model it yourself | **first-class, with expiry and actor type** |
"""
    )

    ctx.boundary(
        """
Determinism is a property of **evaluation**, not of the system. The planner
above is still non-deterministic, the network is still unreliable, and the
adapter still decides what to ask.

What determinism buys you is narrower and more valuable than it sounds: given
the same contract, request, and instant, you can reproduce any past decision
exactly — which is what makes an incident reconstructible and a drift gate
meaningful.
"""
    )

    ctx.tryit(
        """
Find `LAB_AS_OF` in `src/nornyx_lab/constants.py` and move it to
`2026-06-09T00:00:00Z` — one day past the approval window. Run
`python scripts/build_contracts.py`. Read the diagnostics carefully, then put it
back. You have just experienced why approvals expire.
"""
    )
