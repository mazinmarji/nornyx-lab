"""Lab 11 — Digests, locks, ordering, and replay.

Generate, lock, tamper, verify. Then look at what the lock still cannot tell you.
"""

from __future__ import annotations

import json

from nornyx.agentic import (
    CapabilityRequest,
    EvaluationContext,
    EvidenceRecorder,
    contract_digest,
)

from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, content_hash, lock_check, shared_contract
from nornyx_lab.engine import LabContext

ATLAS = shared_contract("atlas")
ID = "identity.research_assistant"


def run(ctx: LabContext) -> None:
    # -------------------------------------------------------------- digests
    ctx.section("What a digest binds — and the five things it does not")

    from nornyx.parser import load_nyx

    document = load_nyx(ATLAS / "network.nyx")
    digest = contract_digest(document)
    ctx.code(f"contract_digest = {digest}", "text", caption="content addressing")

    ctx.concept(
        "a digest binds content and nothing else",
        """
It establishes: **this exact content**, unchanged.

It does **not** establish:

1. **Authorship** — who wrote it. Anyone can hash anything.
2. **Authority** — that whoever wrote it was allowed to.
3. **Time** — when it existed. A digest has no clock.
4. **Correctness** — a perfectly hashed contract can be wrong.
5. **Completeness** — that this is all the content there was (Lab 02).

Every one of those requires a *different* mechanism. Signatures buy authorship;
a timestamping authority buys time; review buys correctness; an ordered stream
with sequence numbers buys completeness within a stream.
""",
    )

    # ----------------------------------------------------------------- lock
    ctx.section("A lock is a multi-way binding")

    lock_path = ATLAS / "nornyx.agentic_network.lock"
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    ctx.say(
        "The agentic-network lock does not bind one thing. It binds several at "
        "once, so that *any* of them moving invalidates the whole:"
    )
    ctx.code(
        json.dumps(
            {k: v for k, v in payload.items() if not isinstance(v, (list, dict))}
            | {
                k: f"<{type(v).__name__}, {len(v)} entries>"
                for k, v in payload.items()
                if isinstance(v, (list, dict))
            },
            indent=2,
        ),
        "json",
        caption="the lock's top level",
    )

    ctx.cli(lock_check(ATLAS / "network.nyx", lock_path, ATLAS / "control_artifacts", cwd=ATLAS))

    # -------------------------------------------------------------- tamper
    ctx.section("Tamper with one generated artifact")

    artifacts = ATLAS / "control_artifacts"
    target = artifacts / "capability_matrix.json"
    original_bytes = target.read_bytes()
    before = content_hash(target)

    ctx.say(
        "We will make the smallest meaningful change: flip one risk label in the "
        "generated capability matrix, the way a hurried engineer might 'fix' a "
        "false positive."
    )
    tampered = original_bytes.replace(b'"risk": "high"', b'"risk": "low"', 1)
    if tampered == original_bytes:
        tampered = original_bytes.replace(b"high", b"low", 1)
    target.write_bytes(tampered)

    ctx.code(
        f"before: {before}\nafter : {content_hash(target)}",
        "text",
        caption="one byte-level edit, a completely different digest",
    )

    result = ctx.cli(
        lock_check(ATLAS / "network.nyx", lock_path, artifacts, cwd=ATLAS),
        expected_fail=True,
    )
    ctx.record("tamper_codes", result.codes())

    # Restore before anything else in the lab (or the suite) runs.
    target.write_bytes(original_bytes)
    restored = ctx.cli(lock_check(ATLAS / "network.nyx", lock_path, artifacts, cwd=ATLAS))
    ctx.record("restored_ok", restored.ok)

    ctx.verdict(
        not result.ok and restored.ok,
        "The lock caught a single-field edit to a generated artifact, and the "
        "check passed again once the bytes were restored. That round trip is the "
        "whole gate.",
    )

    ctx.say(
        "Byte-determinism is what makes this possible. If `generate` produced a "
        "timestamp or a randomly ordered map, this comparison would fail at random, "
        "and a gate that fails at random gets deleted within a month. **A "
        "nondeterministic generator destroys drift detection.**"
    )

    # ------------------------------------------------------------- ordering
    ctx.section("Ordering, within one stream")

    az = authorizer_for(ATLAS)
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )
    recorder = EvidenceRecorder(az, eval_ctx, producer_id="nornyx-lab.integrity")
    for _ in range(3):
        recorder.record_decision(
            az.evaluate(CapabilityRequest(ID, "search_web"), context=eval_ctx),
            mission_id="mission.ordering",
        )
    events = recorder.stream()["events"]
    ctx.say(f"Recorded **{len(events)} events**, sequences `{[e['sequence'] for e in events]}`.")

    ctx.say(
        """
Four checks are available *inside a single-producer stream*, and each rules out
exactly one thing:

| check | rules out |
|---|---|
| contiguous sequence | a dropped record |
| monotonic sequence | a reordered record |
| one outcome per attempt | a decision reported twice with different results |
| no retry after success | an attempt resurrected after it completed |

And the limit that matters: **local ordering cannot establish distributed
causality.** Two producers each emitting a perfectly ordered stream tell you
nothing about which event happened first across them. For that you need a
shared clock discipline or a causal token — neither of which a per-stream
sequence number is.
"""
    )

    # ------------------------------------------------------------- identity
    ctx.section("Mission, operation, occurrence, attempt")

    ctx.say(
        """
Four levels, because "did this happen twice?" has four different answers:

| level | question it answers | example |
|---|---|---|
| **mission** | which piece of work is this part of? | remediate CASE-1041 |
| **operation** | which logical step? | issue the refund |
| **occurrence** | which scheduled execution of that step? | the retry after the timeout |
| **attempt** | which try within that occurrence? | attempt 2 of 3 |

Now classify a pair of similar events:

- same operation, same occurrence, attempt 1 and 2 → a **retry**
- same operation, different occurrence → **repeated work** (a loop visit)
- same operation, same occurrence, same attempt, twice → a **duplicate**, and
  the second one is either a replay or a bug

Without occurrence identity, a legitimate retry and a replay attack are the same
bytes. That is why Chapter 20 insists a runtime-event schema must carry
execution identity.
"""
    )

    ctx.concept(
        "replay detection by fingerprint",
        """
A semantic fingerprint hashes the *meaningful* fields of an event and excludes
the ones that legitimately differ between honest repetitions — the attempt
counter, the timestamp, the event id.

Get the exclusion set wrong in one direction and honest retries look like
attacks; wrong in the other and a replay slides through. The exclusion set is
therefore part of the schema version, not a tuning knob — which is why a legacy
stream is never silently upgraded to a newer mode.
""",
    )

    ctx.boundary(
        """
**What the lock does not prove.** It binds the contract, the composition, the
generated artifacts, and the schema versions to one another.

It says nothing about whether the runtime *used* them. A process can load a
perfectly valid lock and then call the payments API directly. The lock covers
the design-time chain; the remainder is carried by coverage (Lab 13) and by
enforcement placement (Lab 09).
"""
    )

    ctx.tryit(
        """
1. Edit `contracts/atlas/governance_evidence/approval_record.json` — change one
   character. Run `nornyx check` and read which digest broke. Then run
   `nornyx-lab seal contracts/atlas/network.nyx` and check again.
2. Ask yourself why `seal` is a *developer convenience* and would be a
   catastrophe as an automatic step in CI.
"""
    )
