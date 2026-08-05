"""Lab 14 — Your first contract, and the wall you hit.

Authoring an `agentic_network` contract from scratch produces a wall of
diagnostics on the first run. This lab walks into it deliberately, because the
diagnostics are the fastest way to learn what the profile actually requires.
"""

from __future__ import annotations

import shutil

from nornyx_lab.constants import LAB_AS_OF
from nornyx_lab.contract import nornyx, seal_evidence, shared_contract
from nornyx_lab.engine import LabContext

STAGES = [
    ("starter", "the naive first attempt"),
    ("with_evidence", "after adding governance_evidence"),
    ("with_profile_names", "after using the names the profile fixes"),
    ("sealed", "after binding evidence digests"),
]


def run(ctx: LabContext) -> None:
    # ---------------------------------------------------------------- blocks
    ctx.section("The blocks, grouped by the question they answer")

    ctx.say(
        """
| block | question |
|---|---|
| `project` | who is this, and what is it explicitly **not**? |
| `intents`, `goals` | what is it for? |
| `contexts` | what may be read, and which sources may *decide*? |
| `policies` | what is forbidden (`deny`) and what is obliged (`require`)? |
| `capabilities` | what bounded actions exist? |
| `agent_identities` | who exists, and what do they hold? |
| `approvals` | who may approve, for what, for how long? |
| `governance_evidence` | what evidence backs this contract? |
| `agentic_network` | zones, memberships, gates, delegations, handoffs, relations |

The **top level is closed** — an unrecognised block is *named and coded* as a
warning (Lab 06). Block *interiors* are open, so profiles can contribute fields.
That asymmetry is deliberate: a typo at the top cannot silently become an
unenforced rule, while a profile can still extend what a block means.
"""
    )

    ctx.concept(
        "the two rule verbs",
        """
```yaml
policies:
  - name: AtlasGovernance
    deny:    [secrets_to_agents, autonomous_approval]
    require: [exact_revision_binding, evidence_before_external_share]
```

- **`deny`** rules are matched at **planning time**, against declared tokens.
  They are how a contract says *this must never be part of a plan*.
- **`require`** rules do **not** execute a check. They become **recorded
  obligations** — statements that something must be true, which the evidence
  layer must then demonstrate.

Misreading `require` as "Nornyx will verify this for me" is the single most
common beginner error. `require: human_approval_for_disbursement` does not make
approvals happen. It records that they must, and makes their absence a finding.
""",
    )

    # ------------------------------------------------------------ the wall
    ctx.section("Walk into the wall")

    work = ctx.dir / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copy(ctx.dir / "stages" / "starter.nyx", work / "network.nyx")

    ctx.code(
        (ctx.dir / "stages" / "starter.nyx").read_text(encoding="utf-8")[:1200],
        "yaml",
        caption="stages/starter.nyx — a reasonable-looking first attempt",
    )

    result = ctx.cli(
        nornyx("check", "network.nyx", "--as-of", LAB_AS_OF, cwd=work),
        expected_fail=True,
        show_output=False,
    )
    codes = result.codes()
    ctx.record("starter_codes", codes)
    ctx.say(f"**{len(codes)} diagnostics.** This is normal, and it is the lesson.")

    ctx.concept(
        "how to read a diagnostic",
        """
```json
{
  "level":     "error",
  "code":      "AN_APPROVAL_DECLARED_ROLE_UNAUTHORIZED",
  "message":   "Document approval roles are absent from the composed module authority: ...",
  "path":      "approvals[0].required_roles",
  "source_id": "agentic_network_foundation.v1"
}
```

- **`code`** is a **public interface**. It is stable across releases, so you can
  gate a pipeline on a specific condition rather than on grepping a message.
- **`path`** is where to edit, in document coordinates.
- **`source_id`** is *which control* objected — the provenance from Lab 07.
- **`level`** distinguishes an error from an auditability warning.
""",
    )

    # ------------------------------------------------------------- the fixes
    ctx.section("Fix it in three moves")

    ctx.say(
        """
The diagnostics cluster into three groups, and each has one cause:

**1. `GOVERNANCE_REQUIRED_BLOCK_MISSING`, `AN_APPROVAL_RECORD_MISSING`,
`AN_CONTRACT_REVIEW_MISSING`** — the profile requires a `governance_evidence`
block with two specific records. A contract that governs money must carry the
evidence that *it* was reviewed.

**2. `AN_APPROVAL_DECLARATION_MISSING`, `AN_APPROVAL_DECLARED_ROLE_UNAUTHORIZED`,
`AN_RELATION_APPROVER_NOT_HUMAN`** — the profile *fixes* the approval's name and
its accountable role. You may not choose your own:

| you must use | not |
|---|---|
| `agentic_network_authority` | `publication_authority` |
| `network_governance_owner` | `research_governance_owner` |

That is a superior layer refusing to be renamed from below — Lab 07's rule,
met in practice.

**3. `AN_APPROVAL_EXPIRY_EXCESSIVE`, `AN_APPROVAL_EXPIRED`** — approvals expire
after **P7D**, and the validation instant must fall inside the window. This is
why every command in this repository passes `--as-of`.
"""
    )

    for stage, description in STAGES[1:]:
        source = ctx.dir / "stages" / f"{stage}.nyx"
        if not source.is_file():
            continue
        shutil.copy(source, work / "network.nyx")
        shutil.copytree(
            shared_contract("atlas") / "governance_evidence",
            work / "governance_evidence",
            dirs_exist_ok=True,
        )
        if stage == "sealed":
            changes = seal_evidence(work / "network.nyx")
            ctx.note(f"sealed {len(changes)} evidence digest(s)")
        stage_result = nornyx("check", "network.nyx", "--as-of", LAB_AS_OF, cwd=work)
        remaining = len(stage_result.codes())
        ctx.cli(stage_result, expected_fail=not stage_result.ok, show_output=False)
        ctx.note(f"{description}: {remaining} diagnostic(s) remaining")
        ctx.record(f"{stage}_codes", stage_result.codes())

    final = nornyx("check", "network.nyx", "--as-of", LAB_AS_OF, cwd=work)
    ctx.record("final_ok", final.ok)
    ctx.verdict(
        final.ok,
        "Contract valid. Every diagnostic named exactly one thing, and fixing "
        "them in order took three edits.",
    )

    # ----------------------------------------------------------- version axes
    ctx.section('Why the file says nornyx: "0.2" under a language called 1.0')

    ctx.say(
        """
Five version axes move independently, and conflating them is how a team breaks
a deployment during a routine upgrade:

| axis | this repo |
|---|---|
| Python distribution | `nornyx` **1.11.0** |
| contract language surface | `nornyx: "0.2"` in the document |
| agentic integration SPI | **1.2** |
| runtime-events schema | **1.1** |
| network lock format | **1.0** |

The `nornyx:` key declares *which language surface this document is written
against*, not which package you installed. They are allowed to differ, and they
do.
"""
    )

    ctx.boundary(
        """
**Read the declared non-goals in your contract's `project` block.** They are not
boilerplate modesty:

> live agent runtime · agent orchestration · agent authentication · tool
> execution · model execution · credential loading · automatic approvals

Every one is a thing this layer will never do, written where a reviewer can hold
you to it. A contract whose non-goals list is empty is a contract that has not
decided what it is.
"""
    )

    ctx.tryit(
        """
`labs/14_first_contract/work/network.nyx` is now a valid contract. Make it
yours:

1. Add a capability `archive_briefing` (risk `low`) and give it to the research
   assistant. Re-check.
2. Add a second identity `identity.reviewer` that holds *only* `draft_briefing`.
   Give it a `contract_fixture` binding. Re-check.
3. Now try to give `identity.reviewer` a capability you did **not** add to its
   zone membership. Which diagnostic fires, and why are `capability_refs` in two
   places not redundant?
"""
    )
