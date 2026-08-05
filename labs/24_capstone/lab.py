"""Lab 24 — Capstone: design, build, verify, and audit Northstar.

Eight deliberate failures, each mapped to the boundary that stops it — and one
that nothing stops.
"""

from __future__ import annotations

import json

from nornyx.agentic import (
    ApprovalAssertion,
    AuthorizerLoadError,
    CapabilityRequest,
    EvaluationContext,
    EvidenceRecorder,
    ZoneCrossingRequest,
    load_authorizer,
)

from nornyx_lab import northstar
from nornyx_lab.constants import (
    APPROVAL_EXPIRES_AT,
    APPROVAL_ISSUED_AT,
    LAB_AS_OF,
    LAB_SUBJECT_REVISION,
)
from nornyx_lab.contract import authorizer_for, lock_check, nornyx, shared_contract
from nornyx_lab.engine import LabContext

ATLAS = shared_contract("atlas")
LEDGER = shared_contract("ledger")


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
    atlas = authorizer_for(ATLAS)
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )

    # ---------------------------------------------------------------- design
    ctx.section("The system, as designed")

    ctx.say(
        """
Five Northstar threads, one governance source:

| thread | what it does | governed by |
|---|---|---|
| **Atlas** | drafts competitor briefings | `contracts/atlas` — 1 identity, 2 zones, 1 egress gate |
| **Ledger** | remediates billing cases | `contracts/ledger` — 4 identities, 2 zones, 4 gates, 1 delegation, 1 handoff |
| **Forge** | authors and merges code | the merge gate you designed in Lab 22 |
| **Gateway** | the egress boundary | `zone.public_web` / `zone.customer_channel` |
| **Charter** | the enterprise policy above all of them | profile + modules, composed (Lab 07) |

**Tier decisions, by consequence:**

| action class | consequence | tier claimed | enforcing component |
|---|---|---|---|
| read a case, draft a briefing | reversible | 1 (declared) | contract only |
| propose a refund | reversible, reviewable | 2 | adapter + authorizer |
| publish externally | **irreversible** | 2 today; **3 required** | adapter today; egress proxy needed |
| issue a refund | **irreversible, financial** | 2 today; **3 required** | adapter today; payments IAM needed |

The last two rows are the honest output of the design: the tier the consequence
*demands* and the tier we can *currently support* are not the same, and the gap
is written down rather than papered over.
"""
    )

    # ------------------------------------------------------------ the build
    ctx.section("The build")

    gates = []
    for name, contract in (("atlas", ATLAS), ("ledger", LEDGER)):
        check = nornyx("check", "network.nyx", "--as-of", LAB_AS_OF, cwd=contract)
        lock = lock_check(
            contract / "network.nyx",
            contract / "nornyx.agentic_network.lock",
            contract / "control_artifacts",
            cwd=contract,
        )
        gates.append(
            (f"{name}: contract check", "allow" if check.ok else "deny", f"exit={check.returncode}")
        )
        gates.append(
            (
                f"{name}: lock verification",
                "allow" if lock.ok else "deny",
                f"exit={lock.returncode}",
            )
        )
    ctx.decisions(gates, "design-time gates across the whole system")
    ctx.record("build_gates_pass", all(g[1] == "allow" for g in gates))

    # ------------------------------------------------- failure injection
    ctx.section("The failure-injection programme — eight deliberate failures")

    results: list[tuple[str, str, str]] = []

    # 1. an unheld capability
    d = atlas.evaluate(
        CapabilityRequest("identity.research_assistant", "publish_external"), context=eval_ctx
    )
    results.append(("1. unheld capability", d.effect.value, d.code.value))

    # 2. an undeclared capability
    d = atlas.evaluate(
        CapabilityRequest("identity.research_assistant", "wire_transfer"), context=eval_ctx
    )
    results.append(("2. undeclared capability", d.effect.value, d.code.value))

    # 3. an ungated zone crossing
    d = atlas.evaluate(
        ZoneCrossingRequest(
            "identity.research_assistant", "zone.research_internal", "zone.public_web"
        ),
        context=eval_ctx,
    )
    results.append(("3. crossing without approval", d.effect.value, d.code.value))

    # 4. an AI approving itself
    d = atlas.evaluate(
        ZoneCrossingRequest(
            "identity.research_assistant",
            "zone.research_internal",
            "zone.public_web",
            _approval(claimed_actor_type="ai_tool"),
        ),
        context=eval_ctx,
    )
    results.append(("4. AI-generated approval", d.effect.value, d.code.value))

    # 5. an approval for a different revision
    d = atlas.evaluate(
        ZoneCrossingRequest(
            "identity.research_assistant",
            "zone.research_internal",
            "zone.public_web",
            _approval(subject_revision="git:" + "0" * 40),
        ),
        context=eval_ctx,
    )
    results.append(("5. approval bound to another revision", d.effect.value, d.code.value))

    # 6. a stale approval
    d = atlas.evaluate(
        ZoneCrossingRequest(
            "identity.research_assistant",
            "zone.research_internal",
            "zone.public_web",
            _approval(issued_at="2026-01-01T00:00:00Z", expires_at="2026-01-08T00:00:00Z"),
        ),
        context=eval_ctx,
    )
    results.append(("6. stale approval", d.effect.value, d.code.value))

    # 7. runtime revision skew
    d = atlas.evaluate(
        CapabilityRequest("identity.research_assistant", "search_web"),
        context=EvaluationContext(
            decision_at=LAB_AS_OF, observed_subject_revision="git:" + "0" * 40
        ),
    )
    results.append(("7. deployment revision skew", d.effect.value, d.code.value))

    # 8. a lock from another contract
    try:
        load_authorizer(
            ATLAS / "network.nyx",
            LEDGER / "nornyx.agentic_network.lock",
            validation_as_of=LAB_AS_OF,
        )
        results.append(("8. substituted lock", "allow", "LOADED — unexpected"))
    except AuthorizerLoadError as exc:
        results.append(("8. substituted lock", "deny", exc.code.value))

    ctx.decisions(results, "eight failures, injected on purpose")
    ctx.record("failures_blocked", sum(1 for r in results if r[1] != "allow"))

    # 9. the one nothing stops
    bypass = ctx.ledger("bypass")
    northstar.issue_refund(bypass, 5000.0)
    ctx.decisions(
        [("9. direct call to the business callable", "allow", "NOT MITIGATED")],
        "and the ninth",
    )
    ctx.record("bypass_completions", bypass.completions("issue_refund"))

    ctx.verdict(
        all(r[1] != "allow" for r in results) and bypass.completions("issue_refund") == 1,
        "Eight of nine injected failures were refused by a named mechanism. The "
        "ninth was not, and this repository says so in its claim register rather "
        "than in a footnote.",
    )

    # ---------------------------------------------------- verification matrix
    ctx.section("The verification matrix")

    recorder = EvidenceRecorder(atlas, eval_ctx, producer_id="nornyx-lab.capstone")
    mission = "mission.capstone"
    for capability in ("search_web", "publish_external"):
        recorder.record_decision(
            atlas.evaluate(
                CapabilityRequest("identity.research_assistant", capability), context=eval_ctx
            ),
            mission_id=mission,
        )
    report = recorder.validate()

    ctx.say(
        f"""
| claim | verifying mechanism | transcript | verdict |
|---|---|---|---|
| the contract is valid at the pinned instant | `nornyx check --as-of` | exit 0 | ✔ |
| artifacts match the contract | `agentic-network lock-check` | exit 0 | ✔ |
| generation is deterministic | regenerate + byte-compare | Lab 17 | ✔ |
| unheld capabilities are denied | `Authorizer.evaluate` | failure 1 | ✔ |
| an AI cannot approve | approval evaluation order | failure 4 | ✔ |
| approvals expire | earliest-applicable-expiry rule | failure 6 | ✔ |
| decisions are recorded and bound | `EvidenceRecorder.validate` | `status: {report["status"]}`, {report["event_count"]} events | ✔ |
| **direct invocation is prevented** | — | failure 9 | **✘ not claimed** |

The last row is the deliverable. A verification matrix whose every row says ✔
has not been built honestly.
"""
    )

    # ---------------------------------------------------------- claim register
    ctx.section("The claim register at signoff")

    register = {
        "system": "Northstar Services",
        "subject_revision": LAB_SUBJECT_REVISION,
        "evaluated_at": LAB_AS_OF,
        "toolchain": {"nornyx": "1.11.0", "nornyx-agentic-adapters": "0.3.0"},
        "claims": [
            {
                "id": "NS-001",
                "statement": "Atlas cannot publish externally without a valid human approval.",
                "tier": 2,
                "surface": "crewai tool_invocation (sync), via the governed wrapper",
                "uncovered": ["direct invocation", "async tool path", "4 other CrewAI surfaces"],
                "falsified_by": "one completed publish with no preceding recorded decision",
            },
            {
                "id": "NS-002",
                "statement": "No single Ledger identity can complete a refund alone.",
                "tier": 2,
                "surface": "declared capabilities and gates in contracts/ledger",
                "uncovered": ["any code path that does not consult the authorizer"],
                "falsified_by": "one identity holding both propose_refund and an ungated issue_refund",
            },
            {
                "id": "NS-003",
                "statement": "Every governed decision is recorded before the action runs.",
                "tier": 2,
                "surface": "calls routed through nornyx-agentic-adapters",
                "uncovered": ["actions taken outside the adapter"],
                "falsified_by": "a k-th business entry with fewer than k recorded decisions",
            },
        ],
        "not_claimed": [
            "that the agent identity is authenticated",
            "that the approver is authenticated",
            "that any recorded event is true",
            "that every path to any effect is covered",
        ],
    }
    out = ctx.dir / "claim_register.json"
    out.write_text(json.dumps(register, indent=2), encoding="utf-8")
    ctx.code(
        json.dumps(register["not_claimed"], indent=2),
        "json",
        caption="the not_claimed array — read this first",
    )
    ctx.record("claims", len(register["claims"]))
    ctx.record("not_claimed", len(register["not_claimed"]))

    # --------------------------------------------------------------- lessons
    ctx.section("What it cost, and where not to do this")

    ctx.say(
        """
**The cost ledger, honestly:**

| cost | what it actually was |
|---|---|
| authoring | two contracts, ~200 lines each, and three rounds of diagnostics |
| pinned versions | `crewai==1.15.4` exactly — every upgrade is now a governance event |
| expertise | someone must understand tiers, or the claims inflate on their own |
| latency | one evaluation per governed call |
| **cognitive load** | the largest cost, and the one nobody budgets |

**Where you should not deploy this machinery:**

- a prototype nobody has shipped
- an agent with no irreversible actions at all
- a system where the effect is already behind a strong IAM boundary and the
  governance layer would only add a second, weaker opinion

**Overgovernance is a failure mode with symptoms**: approvals granted in under
five seconds, contracts nobody reads, exceptions that outlive their owners, and
engineers routing around the layer to ship. If you see those, the answer is to
gate *fewer* actions, not to add process.

**The road from Tier 2 to Tier 3**, in dependency order:

1. authenticate the agent identity — workload identity, not an asserted string
2. move the irreversible effect behind a boundary the process cannot cross
3. have that boundary attest independently, in its own store
4. reconcile the two evidence streams — and budget for the fact that they will
   sometimes disagree

Step 2 is where most of the value is, and it is not a Nornyx feature. It is an
architecture change that this layer's declarations tell you *where* to make.
"""
    )

    ctx.boundary(
        """
**The five design judgements this capstone validated**, and the mechanism that
carried each:

1. *Split proposing from executing* — carried by two capabilities, not one.
2. *Bind approvals to a revision* — carried by `subject_revision` checks.
3. *Make time an input* — carried by `--as-of` and `decision_at`.
4. *Publish what is uncovered* — carried by the coverage inventory.
5. *Refuse to claim Tier 3* — carried by nothing, which is the point. It is a
   discipline, and the only thing that maintains it is people who would rather
   ship a narrow true sentence than a broad false one.

You have now run every mechanism in this book against real code. The last one is
the only one you cannot install.
"""
    )

    ctx.tryit(
        """
Take one agent in your own system and produce the three artifacts from this lab:

1. a **contract** — identities, capabilities, zones, gates, approvals
2. a **claim register** — with `uncovered` and `falsified_by` filled in first
3. a **failure-injection programme** — eight failures, each mapped to the
   boundary that stops it, and at least one that nothing does

If you cannot find a failure that nothing stops, look harder. Every Tier 2
system has one, and knowing which is the difference between governance and
decoration.
"""
    )
