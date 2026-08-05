"""Lab 05 — Trust zones, and prompt injection as authority confusion.

The Lab 00 attack, run again — this time against a declared boundary.
"""

from __future__ import annotations

from nornyx.agentic import (
    DataShareRequest,
    EvaluationContext,
    ZoneCrossingRequest,
)

from nornyx_lab import northstar
from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.engine import LabContext

ATLAS_ID = "identity.research_assistant"
INTERNAL = "zone.research_internal"
PUBLIC = "zone.public_web"


def run(ctx: LabContext) -> None:
    az = authorizer_for(shared_contract("atlas"))
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )

    # ---------------------------------------------------------------- zones
    ctx.section("A zone is a declared governance boundary")

    ctx.concept(
        "not a network segment",
        """
A trust zone is **declared**, not inherited from infrastructure. Two agents in
the same Kubernetes namespace, the same process, and the same VPC can sit in
different zones — and two agents on different continents can sit in one.

What a zone carries that a subnet does not:

- **membership** — which identities are in it, holding what, until when
- **allowed transitions** — which other zones it may reach at all
- **a share allowlist** — what categories of content may cross
- **never-share categories** — what may never leave, under any approval
- **ingress and egress gates** — where a crossing is evaluated

`never_share` must be non-empty. A boundary with nothing it refuses to emit is
not a boundary; it is a label.
""",
    )

    text = (shared_contract("atlas") / "network.nyx").read_text(encoding="utf-8")
    start = text.index("  trust_zones:")
    ctx.code(text[start : text.index("  memberships:")], "yaml", caption="the zone map")

    # ------------------------------------------------------------- crossing
    ctx.section("The Lab 00 attack, against a boundary")

    ctx.say(
        "Same hostile page. Same susceptible planner. This time the publish step "
        "has to cross from `research_internal` to `public_web`."
    )

    governed = ctx.ledger("governed")
    ungoverned = ctx.ledger("ungoverned")

    page = northstar.search_web(ungoverned, "competitor pricing", hostile=True)
    northstar.search_web(governed, "competitor pricing", hostile=True)
    plan = ctx.planner.plan("Write a briefing on the competitor", page)

    rows = []
    for call in plan.calls:
        if call.action == "search_web":
            continue
        if call.action in {"publish_external", "external_share"}:
            decision = az.evaluate(
                ZoneCrossingRequest(ATLAS_ID, INTERNAL, PUBLIC), context=eval_ctx
            )
            governed.decision(decision.code.value, decision.effect.value)
            rows.append((f"crossing for {call.action}", decision.effect.value, decision.code.value))
            if decision.allowed:
                northstar.perform(governed, call.action, **call.args)
        else:
            northstar.perform(governed, call.action, **call.args)
        northstar.perform(ungoverned, call.action, **call.args)

    ctx.decisions(rows, "evaluated at the egress gate")
    ctx.compare(ungoverned, governed, actions=["search_web", "draft_briefing", "publish_external"])

    ctx.record("governed_publish", governed.completions("publish_external"))
    ctx.record("ungoverned_publish", ungoverned.completions("publish_external"))
    ctx.verdict(
        governed.completions("publish_external") == 0,
        "The planner was fooled in both runs — identical plans. Only one of them "
        "reached the outside world.",
    )

    # -------------------------------------------------------------- sharing
    ctx.section("What may cross, and what never may")

    share_rows = []
    for label, categories in [
        ("evidence_digest", ("evidence_digest",)),
        ("briefing_draft (internal-only category)", ("briefing_draft",)),
        ("credentials", ("credentials",)),
        ("secrets + evidence_digest", ("secrets", "evidence_digest")),
    ]:
        decision = az.evaluate(
            DataShareRequest(ATLAS_ID, ATLAS_ID, categories, INTERNAL, PUBLIC),
            context=eval_ctx,
        )
        share_rows.append(
            (f"share {label} → public_web", decision.effect.value, decision.code.value)
        )
    ctx.decisions(share_rows, "the same crossing, four payloads")

    ctx.say(
        "`SHARE_NOT_ALLOWED` and `SENSITIVE_SHARING` are different refusals on "
        "purpose. The first says *this zone does not carry that category*; the "
        "second says *nothing carries this, ever* — no approval unlocks it."
    )

    # ------------------------------------------------------------- authority
    ctx.section("Origin, authority, taint — and why relevance is not authority")

    ctx.say(
        """
Model every context item on three axes:

| item | origin | authority | taint |
|---|---|---|---|
| `network.nyx` | the repository, reviewed | **decides** | trusted |
| `docs/refund_policy.md` | the repository, reviewed | **decides** | trusted |
| the retrieved web page | the open internet | **informs only** | untrusted |
| the user's prompt | a human, unauthenticated to the agent | informs only | untrusted |

Prompt injection is not a model defect to be patched. It is **authority
confusion**: text that should only inform arrives in the same channel as text
that decides, and nothing in the channel marks which is which.

The fix is not "make the model resist better". A model that resists 99% of
injections is a model that fails on the attempt that matters. The fix is that
the *action* the injected text asks for must cross a boundary that never asked
the model's opinion.
"""
    )

    ctx.code(
        """contexts:
  - name: ResearchContext
    include: [README.md, briefings/**/*.md]   # what may be READ
    exclude: [.env, secrets/**]               # what may never be read
    authority: [network.nyx]                  # what may DECIDE""",
        "yaml",
        caption="include is readability; authority is decision rights",
    )

    ctx.boundary(
        """
**The zone stopped the crossing. It did not stop the injection.**

The planner still read the hostile text, still believed it, and still proposed
publishing. Nothing here cleans input or improves the model. Everything here
assumes the model will be fooled and makes that survivable.

And note the coverage question underneath: this held because the publish path
went through the evaluated crossing. A second path to the same effect — an HTTP
client the agent can call directly — is not covered by anything you have seen
so far. That is Lab 13.
"""
    )

    ctx.tryit(
        """
1. Add `briefing_draft` to `zone.public_web`'s `share_allowlist`, rebuild with
   `python scripts/build_contracts.py atlas`, and re-run. Which decision changed?
2. Now try adding `secrets` to the same allowlist. Rebuild and re-run. Why does
   the decision *not* change — and which line in the contract is responsible?
"""
    )
