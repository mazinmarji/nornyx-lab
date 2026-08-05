"""Lab 23 — Threats, standards, audit packages, and honest limits.

The chapters most likely to be skimmed, and the ones an auditor reads first.
"""

from __future__ import annotations

import json

from nornyx.agentic import CapabilityRequest, EvaluationContext, EvidenceRecorder

from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, lock_check, nornyx, shared_contract
from nornyx_lab.engine import LabContext

ATLAS = shared_contract("atlas")


def run(ctx: LabContext) -> None:
    az = authorizer_for(ATLAS)
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )

    # -------------------------------------------------------------- assets
    ctx.section("Six asset classes — only one of which most threat models list")

    ctx.say(
        """
| # | asset | what an attacker gains by reaching it |
|---|---|---|
| 1 | **data** | the only one most models enumerate |
| 2 | **the contract** | change what is permitted, permanently |
| 3 | **the lock** | make a modified artifact set look verified |
| 4 | **approval records** | manufacture authority after the fact |
| 5 | **the evidence store** | rewrite what happened |
| 6 | **the claims and the coverage matrix** | make an unguarded surface look guarded |

Asset 6 is the one nobody protects, and it is the one that scales: an inflated
claim causes teams to *stop looking* at a surface. The attacker does not need to
break anything — they need you to believe it is already covered.
"""
    )

    ctx.say(
        """
**Six attacker models**, and which assets each is positioned to reach:

| attacker | position | reaches |
|---|---|---|
| external content author | writes a page your agent retrieves | the planner (Lab 05) |
| malicious tool package | inside your dependency tree | the process, assets 1–5 (Lab 20) |
| compromised agent process | inside the trust domain | assets 1–5; **cooperative controls do not stop this** |
| insider with commit rights | the repository | assets 2, 3, 6 |
| insider with approval rights | the approval flow | asset 4 |
| a well-meaning engineer under deadline | everywhere | asset 6, by writing a claim nobody checks |

The last row is not a joke. Most coverage regressions are authored by people
trying to ship.
"""
    )

    # -------------------------------------------------------- threat trees
    ctx.section("Two threat trees, with the mechanism that stops each branch")

    ctx.say(
        """
**Subvert the contract** — make the system permit something it should not:

```
subvert the contract
├── edit it directly ......................... commit review + branch protection
├── widen a superior control ................. REFUSED by composition        (Lab 07)
├── smuggle execution into a declaration ..... structurally unrepresentable  (Lab 17)
├── add an unrecognised block ................ DETECTED (warning), not blocked (Lab 06)
└── swap the lock for one you built .......... lock verified against THIS contract (Lab 15)
```

**Subvert the record** — make it look like something else happened:

```
subvert the record
├── edit an evidence file .................... content_hash breaks           (Lab 11)
├── drop an event ............................ sequence gap                  (Lab 11)
├── replay an event .......................... occurrence + attempt identity (Lab 17)
├── forge an approval ........................ revision + role + actor-type checks (Lab 08)
└── never write the event at all ............. NOT MITIGATED — Tier 2 ceiling (Lab 12)
```

Two branches deserve a second look. "Add an unrecognised block" is **detected
but not blocked** — a warning with a stable code, which your pipeline may choose
to treat as fatal. "Never write the event at all" has **no mechanism at all**.

Saying both out loud is the point of the exercise.
"""
    )

    rows = []
    # Each row is one branch above, exercised for real.
    original = (ATLAS / "network.nyx").read_text(encoding="utf-8")

    probe = ATLAS / "threat_probe.nyx"
    probe.write_text(
        original.replace(
            "denied_actor_types: [ai_tool, execution_surface, autonomous_agent, model, connector, generated_output]",
            "denied_actor_types: [connector]",
        ),
        encoding="utf-8",
    )
    r = nornyx("check", "threat_probe.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS)
    rows.append(
        (
            "widen a superior control",
            "deny" if not r.ok else "allow",
            r.codes()[0] if r.codes() else "?",
        )
    )

    probe.write_text(original + "\nbackdoor:\n  - name: skip_everything\n", encoding="utf-8")
    r = nornyx("check", "threat_probe.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS)
    unknown = [d for d in r.diagnostics() if d.get("code") == "UNKNOWN_TOP_LEVEL_BLOCK"]
    # Detected, not blocked: the check still exits 0. Gating on it is your call.
    rows.append(
        (
            "add an unrecognised block",
            "approval_required" if (unknown and r.ok) else ("deny" if not r.ok else "allow"),
            f"{unknown[0]['code']} ({unknown[0]['level']})" if unknown else "undetected",
        )
    )
    probe.unlink(missing_ok=True)

    r = lock_check(
        ATLAS / "network.nyx",
        shared_contract("ledger") / "nornyx.agentic_network.lock",
        ATLAS / "control_artifacts",
        cwd=ATLAS,
    )
    rows.append(
        (
            "swap in another contract's lock",
            "deny" if not r.ok else "allow",
            r.codes()[0] if r.codes() else "non-zero exit",
        )
    )

    d = az.evaluate(
        CapabilityRequest("identity.research_assistant", "publish_external"), context=eval_ctx
    )
    rows.append(("use an unheld capability", d.effect.value, d.code.value))

    ctx.decisions(rows, "threat branches, actually attempted")
    ctx.record("threat_branches_blocked", sum(1 for r in rows if r[1] == "deny"))

    # ----------------------------------------------------------- standards
    ctx.section("A mapping row that is checkable")

    ctx.say(
        """
A standards mapping is an **interpretive argument**, and it can be wrong. Seven
fields make one checkable — and most published mappings omit the last three:

| field | this row |
|---|---|
| **control reference** | *(the clause you are mapping to)* |
| **our mechanism** | zone-crossing evaluation at the egress gate |
| **the artifact** | `contracts/atlas/network.nyx`, `gate.publication_review` |
| **the evidence** | validated runtime-event stream, `status: pass` |
| **the surface it covers** | the CrewAI synchronous tool path only |
| **the caveats** | cooperative Tier 2; direct invocation uncovered; identity asserted, not authenticated |
| **who signed off** | *(a named human, with a date)* |

Drop the last three and you have compliance-washing: a table that reads as
conformity and asserts nothing falsifiable.

Three anti-patterns to recognise in mappings you receive **and the ones you
write**:

1. **checkbox mapping** — one control claimed against twelve clauses, with no
   surface named.
2. **tool-implies-conformity** — "we use *X*, therefore clause 6.1 is met".
3. **scope laundering** — the mechanism covers one surface; the row implies the
   system.
"""
    )

    # --------------------------------------------------------- audit package
    ctx.section("Assemble an auditor-facing package")

    recorder = EvidenceRecorder(az, eval_ctx, producer_id="nornyx-lab.audit")
    mission = "mission.audit-sample"
    recorder.record_decision(
        az.evaluate(
            CapabilityRequest("identity.research_assistant", "search_web"), context=eval_ctx
        ),
        mission_id=mission,
    )
    recorder.record_decision(
        az.evaluate(
            CapabilityRequest("identity.research_assistant", "publish_external"), context=eval_ctx
        ),
        mission_id=mission,
    )
    report = recorder.validate()

    out = ctx.dir / "audit-package"
    out.mkdir(parents=True, exist_ok=True)
    (out / "runtime_events.json").write_text(
        json.dumps(recorder.stream(), indent=2), encoding="utf-8"
    )
    (out / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    claim_register = {
        "subject_revision": LAB_SUBJECT_REVISION,
        "evaluated_at": LAB_AS_OF,
        "claims": [
            {
                "id": "CLAIM-001",
                "statement": (
                    "On the CrewAI synchronous tool surface, a publish attempt is denied "
                    "without a valid human approval bound to this revision."
                ),
                "tier": 2,
                "surface": "crewai tool_invocation (sync)",
                "mechanism": "nornyx.agentic Authorizer via nornyx-agentic-adapters 0.3.0",
                "evidence": ["runtime_events.json", "validation_report.json"],
                "uncovered": [
                    "direct invocation of the business callable",
                    "crewai async tool path (_arun)",
                    "5 of 6 declared CrewAI surfaces",
                ],
                "falsified_by": ("one completed publish with no preceding recorded decision"),
                "signed_off_by": "<name>, <date>",
            }
        ],
    }
    (out / "claim_register.json").write_text(json.dumps(claim_register, indent=2), encoding="utf-8")
    (out / "READING_GUIDE.md").write_text(
        "# Reading guide\n\n"
        "1. `claim_register.json` — what is claimed, and what is explicitly not.\n"
        "2. `validation_report.json` — the validator's own stated limitations.\n"
        "3. `runtime_events.json` — the bound event stream.\n"
        "4. `../../contracts/atlas/` — contract, lock, and generated artifacts.\n\n"
        "Read the claim register first. Every other file is evidence *for a claim*, "
        "and evidence without a claim to test is just data.\n",
        encoding="utf-8",
    )

    ctx.code(
        json.dumps(claim_register["claims"][0], indent=2),
        "json",
        caption="the claim register — the first file an auditor should open",
    )
    ctx.record("audit_files", sorted(p.name for p in out.iterdir()))

    ctx.say(
        """
Three anti-patterns that make an audit package worthless:

1. **no claim register** — a pile of evidence with nothing to test it against.
2. **evidence without a subject revision** — cannot be tied to a version of anything.
3. **failed packages deleted** — a preserved failure is evidence; a deleted one
   is a gap in the record, and an auditor will read it as the latter.
"""
    )

    # ------------------------------------------------------------- adoption
    ctx.section("Adoption, cost, and what is not yet permitted to be claimed")

    ctx.say(
        """
| stage | you may now claim | you may **not** yet claim |
|---|---|---|
| 1 declared | "our policy is written and versioned" | that anything enforces it |
| 2 checked in CI | "contracts are valid and artifacts do not drift" | anything about runtime |
| 3 one surface wrapped | "*this surface* is governed at Tier 2" | "our agents are governed" |
| 4 evidence validated | "decisions on that surface are recorded and bound" | that the events are true |
| 5 independent enforcement | "*this effect* cannot occur unauthorized" | that every effect is covered |

The honest cost ledger, which vendors omit: **authoring effort** (a real contract
is a week, not an afternoon), **pinned-version maintenance** (an exact framework
pin means you own every upgrade as a governance event), **scarce expertise**, and
**latency** on every governed call.
"""
    )

    ctx.boundary(
        """
**Eight open problems this discipline has not solved** — not criticisms from
outside, but limits stated from within:

1. Cooperative enforcement cannot bind hostile in-process code.
2. Identity is asserted by the adapter; binding it to a real principal is unsolved here.
3. Evidence is self-reported; independent attestation needs a separate trust domain.
4. Distributed causality across producers is not established by local ordering.
5. Semantic drift between a policy and its projection into another language.
6. Approval fatigue has no mechanical fix, only economic ones.
7. Standards mappings remain interpretive and can be wrong.
8. Coverage completeness is undecidable — you cannot enumerate every path.

Publishing this list **strengthens** the claims that remain. A project that
states what would falsify its own tier claims is one whose other claims you can
weigh.
"""
    )

    ctx.tryit(
        """
Build the audit package for one real claim in your own system:

1. Write the claim in the eight-element form from Lab 12.
2. List the evidence that supports it, and the surface it covers.
3. Write the `uncovered` array **before** the `evidence` array.

If `uncovered` is empty, you have not finished step 3.
"""
    )
