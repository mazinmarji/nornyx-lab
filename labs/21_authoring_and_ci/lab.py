"""Lab 21 — The authoring workflow and the CI gate set.

How a contract change gets reviewed, and what a pipeline must run so that
"governed" survives the next pull request.
"""

from __future__ import annotations

import shutil

from nornyx_lab.constants import LAB_AS_OF
from nornyx_lab.contract import generate, lock_check, nornyx, shared_contract
from nornyx_lab.engine import LabContext

ATLAS = shared_contract("atlas")


def run(ctx: LabContext) -> None:
    ctx.section("Authoring is a software lifecycle")

    ctx.say(
        """
| stage | command | what it establishes |
|---|---|---|
| **draft** | your editor | intent |
| **check** | `nornyx check --as-of` | structural + governance validity |
| **generate** | `nornyx agentic-network generate` | the derived artifacts |
| **review** | a human, on **three** diffs | that the change is what was meant |
| **merge** | your VCS | the change is adopted |
| **lock** | `nornyx agentic-network lock` | the whole set is bound together |

Skipping *review* is the interesting failure: everything else is mechanical, and
the mechanical parts all pass on a change that is perfectly valid and completely
wrong.
"""
    )

    # ---------------------------------------------------------- three diffs
    ctx.section("A contract review needs three diffs, not one")

    ctx.say(
        """
| diff | answers | you miss this if you skip it |
|---|---|---|
| **source** | what did the author write? | nothing — but it is the least informative |
| **effective governance** | what is now *in force*, after composition? | a module upgrade changed your controls and the source diff is empty |
| **generated artifacts** | what will downstream consumers now read? | a one-line source edit rewrote the agent's instructions |

Reviewing only the source diff is the common practice and the unsafe one. A
contract's source can be unchanged while its effective governance moves, because
composition pulls in modules whose versions are pinned elsewhere.
"""
    )

    ctx.say("Produce the second and third for the Atlas contract:")
    ctx.cli(
        nornyx("governance", "explain", "network.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS),
        show_output=False,
    )

    scratch = ctx.dir / "artifacts-now"
    shutil.rmtree(scratch, ignore_errors=True)
    ctx.cli(generate(ATLAS / "network.nyx", scratch, cwd=ATLAS), show_output=False)
    produced = sorted(p.name for p in scratch.iterdir() if p.is_file())
    ctx.note(f"{len(produced)} generated artifacts to diff against the committed set")
    shutil.rmtree(scratch, ignore_errors=True)

    ctx.concept(
        "the two rule verbs, and how they mis-match",
        """
`deny` matches **tokens** at planning time. That means it can:

- **overmatch** — `deny: external_share` also catches a benign internal share
  that happens to use the token, and the author never intended that.
- **undermatch** — `deny: publish_external` does nothing about
  `syndicate_briefing`, because nobody wrote that token down.

You cannot fix this by wording the rule more carefully. You fix it with **tests
that establish intent**: for each rule, one case that must be denied and one
neighbouring case that must not. Those tests are the review artifact; the rule
text alone is not reviewable.
""",
    )

    # -------------------------------------------------------------- the gates
    ctx.section("The gate set")

    ctx.say(
        """
| gate | command | proves | scope it does NOT cover |
|---|---|---|---|
| **check** | `nornyx check --as-of` | the contract is structurally and governance valid | nothing at run time |
| **drift** | regenerate + byte-compare | committed artifacts match the contract | that anything used them |
| **lock verification** | `agentic-network lock-check` | contract, composition, artifacts agree | that the runtime loaded this lock |
| **evidence validation** | `agentic-network evidence-validate` | supplied events are well-formed and bound | that the events are true |
| **conformance** | `python -m nornyx_agentic_adapters.conformance --require …` | the adapter behaves as its inventory claims | your deployment's wiring |
| **zero-skip** | count expected vs executed tests | the suite asserted something | that the assertions are good ones |

Each row's right-hand column is the part teams forget, and it is the part that
turns a green pipeline into a false claim.
"""
    )

    ctx.say("Run the gates against this repository, now:")
    gates = [
        ("check", nornyx("check", "network.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS)),
        (
            "lock-check",
            lock_check(
                ATLAS / "network.nyx",
                ATLAS / "nornyx.agentic_network.lock",
                ATLAS / "control_artifacts",
                cwd=ATLAS,
            ),
        ),
    ]
    rows = [(name, "allow" if r.ok else "deny", f"exit={r.returncode}") for name, r in gates]

    # the drift gate, run for real
    fresh = ctx.dir / "drift-probe"
    shutil.rmtree(fresh, ignore_errors=True)
    generate(ATLAS / "network.nyx", fresh, cwd=ATLAS)
    committed = {
        p.name: p.read_bytes() for p in (ATLAS / "control_artifacts").iterdir() if p.is_file()
    }
    regenerated = {p.name: p.read_bytes() for p in fresh.iterdir() if p.is_file()}
    clean = committed == regenerated
    shutil.rmtree(fresh, ignore_errors=True)
    rows.append(
        ("drift (byte-compare)", "allow" if clean else "deny", "clean" if clean else "DRIFT")
    )

    ctx.decisions(rows, "this repository's own gates")
    ctx.record("gates_pass", all(r[1] == "allow" for r in rows))

    ctx.concept(
        "exit codes and diagnostic codes are public interfaces",
        """
A pipeline gates on `AN_LOCK_ARTIFACT_MISMATCH`, never on grepping the word
"mismatch" out of a human-readable message that a future release may reword.

That stability is what lets a gate be **specific**: fail the build on a lock
mismatch, but route an auditability *warning* to a review queue instead. A gate
that can only distinguish zero from non-zero has to treat both the same way, and
teams respond by turning it off.
""",
    )

    # ---------------------------------------------------------- zero-skip
    ctx.section("Making a skipped test fail closed")

    ctx.say(
        """
The subtlest CI failure in this whole subject: a test that skips because an
optional dependency is missing reports **green**. The gate built on it is now
asserting nothing.

Two mechanical fixes, both in this repository:

```bash
# 1. the adapter suite refuses to skip a framework you named
python -m nornyx_agentic_adapters.conformance --require crewai --require langgraph

# 2. the pipeline counts what ran and fails if the count drops
pytest labs tests -q -rs      # -rs prints every skip with its reason
```

`.github/workflows/ci.yml` in this repo installs both framework extras precisely
so that **zero** tests skip in CI. If a skip appears, it is a finding.
"""
    )

    # -------------------------------------------------------- release gates
    ctx.section("Release governance that fails closed")

    ctx.say(
        """
The same discipline applied to publishing:

| control | fails closed by |
|---|---|
| **trusted publishing** (OIDC, no stored token) | there is no long-lived secret to steal or misuse |
| **strict tag-format gate** | a malformed tag is not eligible to publish at all |
| **tag-to-version binding** | a tag that disagrees with the package version stops the release |
| **version locations enforced by tests** | a version bumped in one file and not another fails the suite |

Each turns a convention into a property. "We always tag correctly" is a
promise; a gate that refuses a malformed tag is a mechanism.
"""
    )

    ctx.boundary(
        """
**Shipping a control and self-applying it are different commitments.**

This lab's gates run against this repository's own contracts. That is a real
claim, and a narrow one: it says the committed artifacts match their contracts
at the pinned instant.

It does not say the lab's own Python is governed by Nornyx — it is not. Nothing
here evaluates a capability before `nornyx-lab` writes a file. Being honest
about which of your own controls you apply to yourself is the point Chapter 29
closes on, and pretending otherwise would be the exact overclaim Lab 12 is about.
"""
    )

    ctx.tryit(
        """
1. Edit one line in `contracts/atlas/network.nyx` — change a capability's `risk`
   from `low` to `medium`. Run the three gates. Which one fails first, and what
   is the exit code?
2. Now run `python scripts/build_contracts.py atlas` and re-run them. You have
   just performed the authoring loop: edit, regenerate, re-lock, re-verify.
3. Read `.github/workflows/ci.yml`. Which gate would have caught a hand-edited
   generated artifact? Which would have caught a stale lock?
"""
    )
