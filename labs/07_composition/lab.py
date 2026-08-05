"""Lab 07 — Composition, provenance, and silent weakening.

Your contract is not the whole policy. Find out what else is in force, where it
came from, and what happens when you try to loosen it.
"""

from __future__ import annotations

from nornyx_lab.constants import LAB_AS_OF
from nornyx_lab.contract import nornyx, shared_contract
from nornyx_lab.engine import LabContext

ATLAS = shared_contract("atlas")


def run(ctx: LabContext) -> None:
    ctx.section("Your contract is the smallest part of your policy")

    ctx.say(
        """
`contracts/atlas/network.nyx` declares one project's rules. What is actually
enforced is that file **composed with** a domain profile and the governance
modules the profile pulls in.

Organizations need this layering because the layers have different owners and
different change cadences — a security module is not revised at the pace of a
product contract. What they must never have is a lower layer quietly loosening
a higher one.
"""
    )

    ctx.cli(nornyx("modules", "list"), show_output=False)
    ctx.cli(nornyx("governance", "explain", "network.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS))

    ctx.concept(
        "three composition operations",
        """
| operation | what it does | precedence |
|---|---|---|
| **merge** | union of independent controls from several packs | order-independent; conflicts are errors, not last-write-wins |
| **override** | a named, explicit replacement of a specific element | only where the superior layer permits it |
| **narrow** | a lower layer makes a control *stricter* | always allowed |

Widening is not on the list. That is the design: a lower layer may narrow but
never silently widen. A necessary weakening must become a **bounded, owned,
expiring exception** — a first-class record, not an edit that deletes a rule.
""",
    )

    # ---------------------------------------------------------- provenance
    ctx.section("Provenance: which pack put this control here?")

    ctx.say(
        "When a control denies your action at 2am, the first question is *who "
        "decided that, and where do I go to argue?* `governance matrix` answers it."
    )
    ctx.cli(nornyx("governance", "matrix", "network.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS))

    ctx.say(
        """
Read the dependency edge in that output: `agentic_network_governance` depends on
`human_approval`. Composition is a **DAG**, resolved in dependency order, and the
order is a property of the declaration rather than of the file system or the
order you happened to list things in.

That determinism is not a nicety. It is the precondition for the next lab: you
cannot lock a composition that composes differently on different machines.
"""
    )

    # ------------------------------------------------------ silent weakening
    ctx.section("Try to weaken a superior control")

    ctx.say(
        "The `human_approval` module requires that an approval explicitly deny every "
        "non-human authority category. Let us try to allow AI tools to approve — the "
        "single most attractive shortcut in this whole subject."
    )

    original = (ATLAS / "network.nyx").read_text(encoding="utf-8")
    weakened = original.replace(
        "denied_actor_types: [ai_tool, execution_surface, autonomous_agent, model, connector, generated_output]",
        "denied_actor_types: [execution_surface, connector]",
    )
    # The probe lives beside the contract so its relative evidence paths resolve.
    probe = ATLAS / "weakened.nyx"
    probe.write_text(weakened, encoding="utf-8")

    ctx.code(
        """  approvals:
    - name: agentic_network_authority
-     denied_actor_types: [ai_tool, execution_surface, autonomous_agent, model, connector, generated_output]
+     denied_actor_types: [execution_surface, connector]""",
        "diff",
        caption="the edit a hurried engineer makes at 5pm",
    )

    result = ctx.cli(
        nornyx("check", "weakened.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS), expected_fail=True
    )
    ctx.record("weakening_codes", result.codes())
    probe.unlink(missing_ok=True)

    ctx.verdict(
        not result.ok,
        "The composition refused. The module's floor is not something a document "
        "below it can lower — and the diagnostic names the exact categories.",
    )

    # ---------------------------------------------------------------- lock
    ctx.section("The profiles lock closes the loop")

    lock_path = ATLAS / "nornyx.profiles.lock"
    if lock_path.is_file():
        text = lock_path.read_text(encoding="utf-8")
        ctx.code(
            text[:900],
            "json" if text.lstrip().startswith("{") else "yaml",
            caption="contracts/atlas/nornyx.profiles.lock",
        )
    ctx.say(
        """
This lock binds **which profile and module versions composed this contract**. It
is a different control from the agentic-network lock you will meet in Lab 11,
which binds the generated artifacts.

Four questions, four different controls — a distinction Chapter 18 makes and
most teams collapse:

| question | control |
|---|---|
| did the contract change? | contract digest |
| did the composed policy change? | **profiles lock** |
| did the generated artifacts change? | agentic-network lock + drift gate |
| did the runtime evidence change? | evidence validation |

Note also that the lock contains **no timestamps**. A lock that embeds "when"
cannot be byte-compared, and a lock you cannot byte-compare is not a gate.
"""
    )

    ctx.boundary(
        """
Composition tells you what is **in force**. It does not tell you what is
**enforced** — every control above is still a design-time artifact.

Nor does provenance tell you the control is *right*. It tells you who to ask.
Chapter 8's honest limit: an auditor can recover which pack contributed a
control and at what version; they cannot recover the argument for why.
"""
    )

    ctx.tryit(
        """
1. Run `nornyx governance matrix contracts/atlas/network.nyx --as-of 2026-06-01T12:00:00Z --json`
   and find the entry for `human_approval`. What version is pinned, and what
   would happen to your lock if it changed?
2. Try to *narrow* instead of widen: add `data_pipeline` to `denied_actor_types`
   and re-check. Does composition object? Why is that asymmetry the whole point?
"""
    )
