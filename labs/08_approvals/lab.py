"""Lab 08 — Approvals: eight ways to not be approved.

One approval assertion, mutated one field at a time. Each mutation produces a
different, specific refusal — and the *order* the checks run in is part of the
interface, not an implementation detail.
"""

from __future__ import annotations

from nornyx.agentic import ApprovalAssertion, EvaluationContext, ZoneCrossingRequest

from nornyx_lab import northstar
from nornyx_lab.constants import (
    APPROVAL_EXPIRES_AT,
    APPROVAL_ISSUED_AT,
    LAB_AS_OF,
    LAB_SUBJECT_REVISION,
)
from nornyx_lab.contract import authorizer_for, shared_contract
from nornyx_lab.engine import LabContext

ID = "identity.research_assistant"
INTERNAL, PUBLIC = "zone.research_internal", "zone.public_web"

VALID = dict(
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


def approval(**overrides) -> ApprovalAssertion:
    fields = dict(VALID)
    fields.update(overrides)
    return ApprovalAssertion(**fields)


def run(ctx: LabContext) -> None:
    az = authorizer_for(shared_contract("atlas"))
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )

    ctx.section("What a durable approval record must carry")

    ctx.code(
        """ApprovalAssertion(
    approval_ref        = "agentic_network_authority",   # WHICH requirement
    claimed_approver_ref= "human.network_governance_owner",  # WHO
    claimed_actor_type  = "human",                       # human, or not
    role                = "network_governance_owner",    # under what authority
    granted             = True,                          # yes or no
    action_ref          = "publish_external",            # for WHAT action
    subject_revision    = "git:5eed1e55…",               # of WHAT exact thing
    issued_at           = "2026-06-01T00:00:00Z",        # WHEN
    expires_at          = "2026-06-08T00:00:00Z",        # until when
    evidence_refs       = ("approval_record", …),        # on what BASIS
)""",
        caption="every field prevents a specific attack",
    )

    ctx.section("The evaluation order, one mutation at a time")

    ctx.say(
        "Below, the **same** crossing request, with one field of the approval "
        "changed each time. Read the codes: each is a different diagnosis."
    )

    mutations = [
        ("valid approval", {}),
        (
            "bound to a different revision",
            {"subject_revision": "git:0000000000000000000000000000000000000000"},
        ),
        ("approves a different action", {"action_ref": "draft_briefing"}),
        ("approver is an AI tool", {"claimed_actor_type": "ai_tool"}),
        ("role outside the composed authority", {"role": "intern"}),
        ("missing required evidence", {"evidence_refs": ("approval_record",)}),
        (
            "issued long ago (relative expiry)",
            {"issued_at": "2026-01-01T00:00:00Z", "expires_at": "2026-01-08T00:00:00Z"},
        ),
        (
            "issued in the future",
            {"issued_at": "2026-07-01T00:00:00Z", "expires_at": "2026-07-08T00:00:00Z"},
        ),
        ("explicitly not granted", {"granted": False}),
    ]

    rows = []
    codes = {}
    for label, override in mutations:
        decision = az.evaluate(
            ZoneCrossingRequest(ID, INTERNAL, PUBLIC, approval(**override)), context=eval_ctx
        )
        rows.append((label, decision.effect.value, decision.code.value))
        codes[label] = decision.code.value
    ctx.decisions(rows, "one field changed per row")
    ctx.record("approval_codes", codes)

    ctx.concept(
        "the order is part of the interface",
        """
The checks run in a fixed sequence: revision binding → action scope → actor type
→ role → evidence → temporal validity → granted.

Order matters because a consumer builds error handling on the *first* failure
they see. If "expired" could sometimes be reported before "wrong revision", a
team would spend the outage renewing an approval that was never for this
artifact in the first place.
""",
    )

    # ------------------------------------------------------ three ways to die
    ctx.section("Expiry, revocation, invalidation are three different things")

    ctx.say(
        """
| | what happened | who acted | how it is detected here |
|---|---|---|---|
| **expiry** | time passed | nobody | `issued_at + P7D`, or an explicit `expires_at` |
| **revocation** | someone withdrew it | the approver or an owner | a `revocations` entry effective at `decision_at` |
| **invalidation** | the *subject* changed underneath it | whoever changed it | `subject_revision` no longer matches |

Invalidation is the subtle one and the most valuable. An approval for revision
`abc123` does not become an approval for `def456` because the change looked
small. Force-push a branch after approval and the approval is gone — not stale,
**not for this thing at all**.
"""
    )

    ctx.say(
        "The engine takes the **earliest applicable expiry** across three sources: "
        "the assertion's own `expires_at`, the declaration's `expires_at`, and "
        "`issued_at + expires_after`. An approval that looks valid on two of them "
        "and stale on the third is stale."
    )

    # ----------------------------------------------------------- non-human
    ctx.section("Why a non-human can never be the approver")

    ctx.say(
        """
Three independent arguments, any one of which is sufficient:

1. **Accountability.** An approval is an assertion that someone will answer for
   the consequence. A model cannot be called to account, sanctioned, or fired.
2. **Independence.** The maker and the checker must be different *authorities*.
   A planner approving its own proposal is one authority twice, whatever the
   architecture diagram shows.
3. **Informedness.** An approver attests they understood what they approved. A
   model asked "approve?" produces a token distribution, not an attestation.

This is why the contract's `denied_actor_types` is not negotiable from below —
you proved that in Lab 07.
"""
    )

    # ------------------------------------------------------- maker-checker
    ctx.section("Maker–checker when the maker is a planner")

    ctx.code(
        """# The trap:
plan  = planner.plan(task, context)            # the MAKER
review= planner.review(plan)                   # the "CHECKER" — same authority
if review.approves: execute(plan)              # one authority, twice

# The rule: directing an agent counts as MAKING. If an engineer prompted the
# agent to open the change, that engineer cannot be its approver either.""",
        caption="separation is over identities and capabilities, not over processes",
    )

    # ------------------------------------------------------------- fatigue
    ctx.section("Approval fatigue is an economics problem")

    approved = ctx.ledger("approved crossing")
    decision = az.evaluate(ZoneCrossingRequest(ID, INTERNAL, PUBLIC, approval()), context=eval_ctx)
    approved.decision(decision.code.value, decision.effect.value)
    if decision.allowed:
        northstar.publish_external(approved, "briefing")

    denied = ctx.ledger("unapproved crossing")
    d2 = az.evaluate(ZoneCrossingRequest(ID, INTERNAL, PUBLIC), context=eval_ctx)
    denied.decision(d2.code.value, d2.effect.value)
    if d2.allowed:
        northstar.publish_external(denied, "briefing")

    ctx.compare(denied, approved, actions=["publish_external"])
    ctx.record("approved_publish", approved.completions("publish_external"))

    ctx.say(
        """
Notice that the approved run **did** publish. Governance is not a machine for
saying no; it is a machine for making yes accountable.

But if an approver is asked to attest forty times a day, the fortieth attestation
is a reflex, and a reflex is not an attestation. That is an **economic** problem,
not a discipline problem, and it has structural fixes: raise the threshold, batch
by consequence band, or reduce how many actions are gated at all. Exhortation is
not among them.
"""
    )

    ctx.concept(
        "bounded exceptions instead of edits",
        """
When a rule genuinely must be relaxed, the wrong move is to edit the rule. The
right move is a first-class **exception record** with four properties:

- an **owner** who is accountable for it
- a **scope** narrower than the rule it suspends
- an **expiry**, so it dies without anyone remembering to kill it
- **evidence** of why it was granted

An edited rule is invisible six months later. An expiring exception shows up on
a report.
""",
    )

    ctx.boundary(
        """
**Nornyx never authenticates the approver.** `claimed_approver_ref` and
`claimed_actor_type` are exactly what they say: claims, supplied by your
application.

The engine checks that the claim is *well-formed, in scope, in role, evidenced,
and unexpired*. Proving that a human named in that record actually pressed a
button is the job of your identity provider and your approval UI. If your
adapter hardcodes `claimed_actor_type="human"`, every check above still passes
and you have governed nothing.
"""
    )

    ctx.tryit(
        """
1. Change `LAB_AS_OF` in `src/nornyx_lab/constants.py` to `2026-06-07T23:59:00Z`
   (one minute before expiry) and re-run. Then `2026-06-08T00:00:01Z`. Which
   code appears, and which of the three expiry sources bound first?
2. Write the eight-field approval record your own system would need for its
   riskiest action. Which field does your current approval flow not capture?
"""
    )
