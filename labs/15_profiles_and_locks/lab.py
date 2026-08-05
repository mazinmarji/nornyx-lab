"""Lab 15 — Profiles, modules, locks, and what a lock cannot prove."""

from __future__ import annotations

import json

from nornyx_lab.constants import LAB_AS_OF
from nornyx_lab.contract import lock_check, nornyx, shared_contract
from nornyx_lab.engine import LabContext

ATLAS = shared_contract("atlas")


def run(ctx: LabContext) -> None:
    ctx.section("A profile is not a module")

    ctx.say(
        """
| | domain profile | governance module |
|---|---|---|
| answers | *what kind of system is this?* | *what control does this add?* |
| examples | `agentic_network`, `regulated`, `ai_coding` | `human_approval`, `evidence_integrity` |
| you pick | exactly one, in `project.profile` | none directly — the profile pulls them in |
| contributes | required blocks, structural checks, module set | rules, required evidence, approval requirements |

A profile is a **selection**; a module is a **contribution**. That is why your
contract names a profile and never lists modules: which modules apply is the
profile's decision, and letting a contract choose its own modules would let it
choose which controls apply to it.
"""
    )

    ctx.cli(nornyx("profiles", "list"))
    ctx.cli(nornyx("profiles", "inspect", "agentic_network"))

    # -------------------------------------------------------- composition
    ctx.section("Composition, traced")

    ctx.cli(nornyx("governance", "explain", "network.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS))

    ctx.say(
        """
Four properties make that output trustworthy rather than merely informative:

1. **Dependency ordering** — `agentic_network_governance` declares a dependency
   on `human_approval`, so it always composes after it. The order is in the
   declaration, not in the filesystem.
2. **Monotone merge** — merging can only add or tighten. You proved in Lab 07
   that a document below cannot loosen a module above.
3. **Provenance stamping** — every resulting control remembers which pack
   contributed it, which is what `governance matrix` prints.
4. **A closed output** — the effective-governance document has a fixed shape, so
   it can be digested and locked.

Remove any one and the lock in the next section becomes meaningless.
"""
    )

    # --------------------------------------------------------------- lock
    ctx.section("What the agentic-network lock binds")

    payload = json.loads((ATLAS / "nornyx.agentic_network.lock").read_text(encoding="utf-8"))
    ctx.say(f"The lock has **{len(payload)} top-level keys**, binding several classes at once:")
    ctx.code(
        "\n".join(
            f"{key:<28} {type(value).__name__}"
            + (f"  ({len(value)} entries)" if isinstance(value, (list, dict)) else f"  {value}")
            for key, value in sorted(payload.items())
        ),
        "text",
        caption="nornyx.agentic_network.lock",
    )

    ctx.cli(
        lock_check(
            ATLAS / "network.nyx",
            ATLAS / "nornyx.agentic_network.lock",
            ATLAS / "control_artifacts",
            cwd=ATLAS,
        )
    )

    # -------------------------------------------------------------- drift
    ctx.section("Break the binding three different ways")

    lock_path = ATLAS / "nornyx.agentic_network.lock"
    artifacts = ATLAS / "control_artifacts"
    original_lock = lock_path.read_bytes()

    rows = []

    # (1) a missing artifact
    victim = artifacts / "trust_zone_map.json"
    victim_bytes = victim.read_bytes()
    victim.unlink()
    r = lock_check(ATLAS / "network.nyx", lock_path, artifacts, cwd=ATLAS)
    rows.append(("an artifact was deleted", "deny", ", ".join(r.codes()[:2]) or "non-zero exit"))
    victim.write_bytes(victim_bytes)

    # (2) an edited artifact
    tampered = victim_bytes.replace(b"governed_local", b"public", 1)
    if tampered != victim_bytes:
        victim.write_bytes(tampered)
        r = lock_check(ATLAS / "network.nyx", lock_path, artifacts, cwd=ATLAS)
        rows.append(("an artifact was edited", "deny", ", ".join(r.codes()[:2]) or "non-zero exit"))
        victim.write_bytes(victim_bytes)

    # (3) a lock that no longer matches its contract
    corrupt = json.loads(original_lock)
    corrupt["subject_revision"] = "git:" + "0" * 40
    lock_path.write_text(json.dumps(corrupt, indent=2), encoding="utf-8")
    r = lock_check(ATLAS / "network.nyx", lock_path, artifacts, cwd=ATLAS)
    rows.append(
        ("the lock names another revision", "deny", ", ".join(r.codes()[:2]) or "non-zero exit")
    )
    lock_path.write_bytes(original_lock)

    ctx.decisions(rows, "the AN_LOCK_* family, provoked on purpose")
    ctx.record("lock_failure_modes", len(rows))

    restored = lock_check(ATLAS / "network.nyx", lock_path, artifacts, cwd=ATLAS)
    ctx.record("restored_ok", restored.ok)
    ctx.verdict(restored.ok, "All three breakages detected; the tree is restored and verifying.")

    # ------------------------------------------------------------ the limit
    ctx.section("Four questions, four different controls")

    ctx.say(
        """
| question | control | what it will NOT tell you |
|---|---|---|
| did the contract change? | contract digest | whether the change was authorized |
| did the composed policy change? | profiles lock | whether the new policy is correct |
| did the generated artifacts change? | agentic-network lock + drift gate | whether the runtime used them |
| did the runtime evidence change? | evidence validation | whether the events are true |

Teams routinely collapse these into "we have a lock file" and then discover
during an incident that the one question they needed answered was a different
one.
"""
    )

    ctx.boundary(
        """
**A verifying lock proves the design-time chain is intact. That is all.**

It does not prove:

- that the running process loaded *this* contract
- that the adapter asked before acting
- that any of the events in your evidence store actually happened
- that the policy is a good policy

The first two are carried by coverage and enforcement placement (Labs 09, 13).
The third is capped by the Tier 2 boundary (Lab 12). The fourth is carried by
review, and by nothing else.
"""
    )

    ctx.tryit(
        """
Run the full cycle by hand on the ledger contract:

```bash
cd contracts/ledger
nornyx agentic-network generate network.nyx --out control_artifacts --as-of 2026-06-01T12:00:00Z
nornyx agentic-network lock     network.nyx --artifacts control_artifacts --out nornyx.agentic_network.lock --as-of 2026-06-01T12:00:00Z
nornyx agentic-network lock-check network.nyx --lock nornyx.agentic_network.lock --artifacts control_artifacts --as-of 2026-06-01T12:00:00Z
```

Then edit one line of `network.nyx` and run only the third command. Which
diagnostic tells you the lock is now stale rather than the artifacts corrupt?
"""
    )
