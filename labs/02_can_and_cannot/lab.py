"""Lab 02 — What governance can and cannot guarantee.

One sentence — "Atlas cannot publish externally without human approval" — taken
apart into the five things it is actually made of, each of which can be true or
false independently of the others.
"""

from __future__ import annotations

import hashlib
import json

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.engine import LabContext

CLAIM = "Atlas cannot publish externally without human approval."


def run(ctx: LabContext) -> None:
    ctx.say(
        f"""
Here is a governance claim. It sounds like one statement:

> **{CLAIM}**

It is five, stacked. Each layer rests on the one below and adds exactly one
thing. Confusing them is how a team ends up believing a system is governed when
only its politest path is.
"""
    )

    from nornyx.agentic import (
        CapabilityRequest,
        EvaluationContext,
        ZoneCrossingRequest,
    )

    az = authorizer_for(shared_contract("atlas"))
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )
    identity = "identity.research_assistant"

    # ------------------------------------------------------------- layer 1
    ctx.section("Layer 1 — declaration:  someone wrote the rule down")

    contract_text = (shared_contract("atlas") / "network.nyx").read_text(encoding="utf-8")
    start = contract_text.index("  - name: publish_external")
    ctx.code(contract_text[start : start + 420], "yaml", caption="contracts/atlas/network.nyx")

    ctx.say(
        "**Establishes:** the rule exists, is machine-readable, and is versioned.\n\n"
        "**Leaves open:** absolutely everything about whether it is obeyed."
    )

    # ------------------------------------------------------------- layer 2
    ctx.section("Layer 2 — decision:  something evaluated the rule")

    rows = []
    d1 = az.evaluate(CapabilityRequest(identity, "publish_external"), context=eval_ctx)
    rows.append(("Atlas asks to publish", d1.effect.value, d1.code.value))

    d2 = az.evaluate(
        ZoneCrossingRequest(identity, "zone.research_internal", "zone.public_web"),
        context=eval_ctx,
    )
    rows.append(("Atlas crosses to the public web", d2.effect.value, d2.code.value))
    ctx.decisions(rows, "real decisions from the loaded authorizer")

    ctx.record("capability_code", d1.code.value)
    ctx.record("crossing_code", d2.code.value)

    ctx.say(
        "**Establishes:** a correct answer was computed.\n\n"
        "**Leaves open:** whether anything acted on it. A decision is a value "
        "returned from a function. On its own it constrains nothing."
    )

    # ------------------------------------------------------------- layer 3
    ctx.section("Layer 3 — observation:  something reported what happened")

    obedient = ctx.ledger("respects decision")
    if d2.allowed:
        northstar.publish_external(obedient, "briefing")

    rogue = ctx.ledger("ignores decision")
    northstar.publish_external(rogue, "briefing")  # never consulted the decision

    ctx.compare(obedient, rogue, actions=["publish_external"])
    ctx.say(
        "Both runs received the **same correct decision**. One honoured it. The "
        "difference is not in the policy engine; it is in whether the action path "
        "goes through a point that applies the decision."
    )
    ctx.record("obedient_completions", obedient.completions("publish_external"))
    ctx.record("rogue_completions", rogue.completions("publish_external"))

    # ------------------------------------------------------------- layer 4
    ctx.section("Layer 4 — evidence binding:  the report is tied to a subject")

    events = [
        {"seq": 1, "type": "capability_requested", "actor": identity},
        {"seq": 2, "type": "capability_denied", "actor": identity, "code": d1.code.value},
    ]
    blob = json.dumps(events, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode()).hexdigest()
    ctx.code(f"{blob}\n\nsha256: {digest}", "text", caption="a bound evidence stream")

    ctx.concept(
        "three independent dimensions",
        """
| dimension | question | moved by |
|---|---|---|
| **integrity** | has this record changed since it was made? | a digest |
| **authenticity** | did the claimed producer really make it? | a signature over that digest |
| **completeness** | is this *all* the records there were? | neither of the above |

They are independent. A perfectly signed, perfectly intact stream can be missing
the one event that mattered — and nothing about the signature will tell you.
""",
    )

    truncated = events[:1]
    t_blob = json.dumps(truncated, sort_keys=True, separators=(",", ":"))
    t_digest = hashlib.sha256(t_blob.encode()).hexdigest()
    ctx.say("Watch completeness fail while integrity holds. Drop the second event and re-digest:")
    ctx.code(f"{t_blob}\n\nsha256: {t_digest}", "text", caption="a stream with one event removed")
    ctx.say(
        f"- Original digest: `{digest[:32]}…`\n"
        f"- Truncated digest: `{t_digest[:32]}…`\n\n"
        "Both are **valid digests of their own content**. A verifier holding only "
        "the truncated stream sees a perfectly intact record. Integrity is intact; "
        "completeness is gone. Signing the truncated stream would add authenticity "
        "and still not help."
    )
    ctx.record("digests_differ", digest != t_digest)

    # ------------------------------------------------------------- layer 5
    ctx.section("Layer 5 — assurance claim:  what you may say out loud")

    ctx.say(
        f"""
Only now can the original sentence be assessed. The defensible version of

> ~~{CLAIM}~~

is

> **On the CrewAI synchronous tool surface, at contract revision
> `{LAB_SUBJECT_REVISION[:20]}…`, a publish attempt that reaches the governed
> wrapper is denied without a valid, unexpired, human approval bound to that
> revision. Attempts that do not traverse the wrapper are not covered.**

Longer, uglier, and true. Lab 12 gives you the tier vocabulary that makes the
qualification compact.
"""
    )

    # ------------------------------------------------------- fail behaviour
    ctx.section("Failure behaviour is part of the guarantee, not an ops detail")

    def evaluate_but_broken(_request):
        raise RuntimeError("policy service unreachable")

    fail_open = ctx.ledger("fail-open")
    try:
        evaluate_but_broken(None)
    except RuntimeError:
        # "Don't block the business on a governance outage."
        northstar.publish_external(fail_open, "briefing")

    fail_closed = ctx.ledger("fail-closed")
    try:
        evaluate_but_broken(None)
    except RuntimeError:
        fail_closed.decision("EVALUATION_UNAVAILABLE", "deny")  # refuse, and say so

    ctx.code(
        """try:
    decision = authorizer.evaluate(request, context=ctx)
except Exception:
    perform(action)              # fail-open  — the outage becomes a grant
    # raise / return DENY        # fail-closed — the outage becomes a refusal
""",
        caption="the same fault, two designs",
    )
    ctx.compare(fail_open, fail_closed, actions=["publish_external"])
    ctx.record("fail_open_completions", fail_open.completions("publish_external"))
    ctx.record("fail_closed_completions", fail_closed.completions("publish_external"))

    ctx.verdict(
        fail_closed.completions("publish_external") == 0,
        "Under an identical fault, one design published and the other refused. "
        "Neither is universally right — but choosing by accident always is wrong.",
    )

    ctx.boundary(
        """
**What Nornyx supplies here, precisely.** Layers 1 and 2: the declaration and a
deterministic decision. It also *validates* supplied evidence at layer 4.

It does not produce layer 3 — your application or an adapter reports what
happened — and it cannot certify layer 5 for you. It never authenticates the
agent or the approver, and it never executes a tool.

That is a **cooperative** boundary. Lab 12 gives it a name and a tier.
"""
    )

    ctx.tryit(
        """
Apply the eight questions to a claim from your own system. Start with the three
that hurt most:

1. **Which exact surface** does the claim cover — and which surfaces exist that
   it does not?
2. **What happens when the enforcing component itself fails?**
3. **Who produced the evidence**, and what would it take for them to be wrong?
"""
    )
