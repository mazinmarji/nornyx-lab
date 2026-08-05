"""Lab 01 — The governance gap.

Four files that each look reasonable, disagree with each other, and are bound to
nothing. Then one file that generates them.
"""

from __future__ import annotations

from nornyx_lab import northstar
from nornyx_lab.contract import nornyx
from nornyx_lab.engine import LabContext


def run(ctx: LabContext) -> None:
    ctx.say(
        """
Northstar's platform team is asked a simple question after the Lab 00 incident:
*what stops an agent from merging code without tests?*

They have an answer. Four of them, actually.
"""
    )

    # ---------------------------------------------------------------- part 1
    ctx.section("Part 1 — the inventory")

    # The control set a real team accumulates. Every one of these was a sensible
    # decision by a competent person on a Tuesday.
    for name, body, lang in [
        ("AGENTS.md — read by the agent", northstar.AGENTS_MD, "markdown"),
        ("policy.yaml — read by compliance", northstar.POLICY_YAML, "yaml"),
        (".github/workflows/ci.yml — read by CI", northstar.CI_SNIPPET, "yaml"),
        ("PR template — read by humans", northstar.REVIEW_CHECKLIST, "markdown"),
    ]:
        ctx.code(body, lang, caption=name)

    ctx.concept(
        "a distributed control system nobody designed",
        """
Look at what you have: four artifacts, four audiences, four update cadences, and
**no protocol between them**. They are not versioned together, no precedence
rule says which wins, and nothing detects that `AGENTS.md` says tests are
optional while `policy.yaml` says they are mandatory.

Chapter 2 calls the accumulated cost **governance debt**. Like technical debt it
compounds quietly — but unlike technical debt, the interest is paid by whoever
is on the other end of an unauthorized action, and the ledger of what you owe is
not in your repository.
""",
    )

    # ---------------------------------------------------------------- part 2
    ctx.section("Part 2 — the agent obeys the file that was written for it")

    ungoverned = ctx.ledger("with AGENTS.md")
    ctx.say(
        "The agent reads `AGENTS.md`, concludes the change is low risk, skips the "
        "tests, and merges."
    )
    northstar.merge_pull_request(ungoverned, "PR-77", tests_passed=False)

    for entry in ungoverned.entries:
        ctx.note(str(entry))

    merged_without_tests = (
        ungoverned.completions("merge_pull_request") == 1
        and ungoverned.entries[0].fields.get("tests_passed") is False
    )
    ctx.record("merged_without_tests", merged_without_tests)
    ctx.verdict(
        not merged_without_tests,
        "Code merged with tests_passed=False. `policy.yaml` said that was "
        "forbidden. Nothing ever showed `policy.yaml` to the agent.",
    )

    # ---------------------------------------------------------------- part 3
    ctx.section("Part 3 — the four kinds of drift")

    ctx.say(
        """
| drift | what moved | the incident you get |
|---|---|---|
| **control** | the enforcement changed, the claim did not | CI turned to `continue-on-error`; the badge still says "tests required" |
| **policy** | two documents state different rules | `AGENTS.md` vs `policy.yaml`, above |
| **configuration** | the deployed config diverged from the reviewed one | staging allows a tool production forbids |
| **framework-adapter** | the framework grew a surface the wrapper never covered | an upgrade adds an async path; the wrapper only wraps sync |

Identifying *which* one an incident exhibits is the skill. They have different
detection mechanisms and different owners.
"""
    )

    # ---------------------------------------------------------------- part 4
    ctx.section("Part 4 — one source, generated artifacts")

    ctx.say(
        """
The alternative is not "write better markdown". It is to make the four artifacts
**derived**, so that disagreeing with each other becomes structurally impossible
rather than merely discouraged.
"""
    )

    contract = ctx.dir / "contract" / "delivery.nyx"
    ctx.code(contract.read_text(encoding="utf-8"), "yaml", caption="contract/delivery.nyx")

    ctx.cli(nornyx("check", str(contract)))
    out = ctx.dir / "generated"
    result = ctx.cli(nornyx("generate", str(contract), "--out", str(out)))

    produced = sorted(p.name for p in out.rglob("*") if p.is_file()) if out.is_dir() else []
    ctx.record("generated_files", produced)
    ctx.say(f"That one contract produced **{len(produced)} artifacts**:")
    for name in produced:
        ctx.note(name)

    agents_md = out / "AGENTS.md"
    if agents_md.is_file():
        text = agents_md.read_text(encoding="utf-8")
        ctx.code(text[:700], "markdown", caption="generated/AGENTS.md — derived, not authored")

    ctx.record("generate_ok", result.ok)

    ctx.concept(
        "derived, not authoritative",
        """
The generated `AGENTS.md` is **not** a document you edit. It is a projection of
the contract, the way a compiled binary is a projection of source. Edit it and
your edit is a bug that the next `generate` deletes.

Lab 17 wires this into a CI gate: regenerate, byte-compare, fail the build on any
difference. That gate is what converts "we keep them in sync" from a promise into
a property.
""",
    )

    ctx.boundary(
        """
**Generation closes policy drift and control drift. It does not close the gap.**

A contract that says `tests_required: true` still does not *stop* an agent from
merging. Nothing here intercepts anything yet — we have made the rules coherent
and single-sourced, which is a design-time property.

Runtime enforcement starts in Lab 09, and the first real interception is Lab 16.
"""
    )

    ctx.tryit(
        """
1. Edit `generated/AGENTS.md` by hand — add a line. Re-run the lab and watch it
   vanish. That is the point.
2. Change `tests_required` in `contract/delivery.nyx` and regenerate. Which of
   the generated files changed? Which audiences just had their instructions
   updated without anyone telling them?
"""
    )
