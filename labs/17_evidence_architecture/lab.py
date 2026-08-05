"""Lab 17 — Occurrence identity, drift gates, and generated artifacts."""

from __future__ import annotations

import json
import shutil

from nornyx.agentic import (
    CapabilityRequest,
    EvaluationContext,
    EvidenceRecorder,
    RuntimeOccurrence,
)

from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, generate, nornyx, shared_contract
from nornyx_lab.engine import LabContext

ATLAS = shared_contract("atlas")
ID = "identity.research_assistant"


def run(ctx: LabContext) -> None:
    az = authorizer_for(ATLAS)
    eval_ctx = EvaluationContext(
        decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION
    )

    # ------------------------------------------------------------- identity
    ctx.section("Why a stream needs execution identity")

    ctx.say(
        """
Two `capability_allowed` events for `issue_refund`, same actor, same mission.
Did the refund happen twice?

Without execution identity you cannot answer. It could be:

- a **retry** — one logical refund, the first attempt timed out
- **repeated work** — a loop legitimately processing two cases
- a **duplicate** — the same event recorded twice, by a bug or a replay

Same bytes, three completely different incidents.
"""
    )

    recorder = EvidenceRecorder.for_occurrences(az, eval_ctx, producer_id="nornyx-lab.occ")
    decision = az.evaluate(CapabilityRequest(ID, "search_web"), context=eval_ctx)

    # one operation, one occurrence, two attempts -> a RETRY
    for attempt in (1, 2):
        recorder.record_occurrence_decision(
            decision,
            mission_id="mission.briefing",
            occurrence=RuntimeOccurrence(
                operation_id="op.search", occurrence_id="occ.1", attempt=attempt
            ),
        )
    # same operation, a DIFFERENT occurrence -> REPEATED WORK
    recorder.record_occurrence_decision(
        decision,
        mission_id="mission.briefing",
        occurrence=RuntimeOccurrence(operation_id="op.search", occurrence_id="occ.2", attempt=1),
    )

    events = recorder.stream()["events"]
    ctx.code(
        json.dumps(events[0]["occurrence"], indent=2),
        "json",
        caption="the occurrence block every event carries in explicit mode",
    )

    rows = [
        (
            f"{e['event_type']}",
            e["occurrence"]["occurrence_id"],
            f"attempt {e['occurrence']['attempt']}",
        )
        for e in events
    ]
    ctx.decisions(rows, "operation op.search, three records")
    ctx.say(
        "Rows 1–2 share an `occurrence_id` and differ in `attempt` — that is a "
        "**retry**. Row 3 has a new `occurrence_id` — that is **repeated work**. "
        "A fourth row identical to row 1 would be a **duplicate**."
    )
    ctx.record("occurrence_events", len(events))
    ctx.record(
        "max_attempt",
        recorder.max_recorded_attempt(
            mission_id="mission.briefing", operation_id="op.search", occurrence_id="occ.1"
        ),
    )

    ctx.concept(
        "the attempt rules",
        """
| rule | what it rules out |
|---|---|
| attempts are **contiguous** from 1 | a silently dropped attempt |
| attempts are **ordered** | a reordered stream |
| **one outcome** per attempt | the same try reported both allowed and denied |
| **no retry after success** | an attempt resurrected after it completed |

Each follows from the identity model rather than from taste: if `attempt` is a
counter within an occurrence, a gap means a record is missing, and a retry after
success means the occurrence identity was reused for different work.
""",
    )

    # --------------------------------------------------------------- modes
    ctx.section("One schema id, two envelope modes")

    legacy = EvidenceRecorder(az, eval_ctx, producer_id="nornyx-lab.legacy")
    legacy.record_decision(decision, mission_id="mission.briefing")

    ctx.code(
        f"""explicit mode : occurrence_mode = {recorder.stream()["occurrence_mode"]!r}
legacy mode   : occurrence_mode = {legacy.stream()["occurrence_mode"]!r}
both declare  : schema = {legacy.stream()["schema"]!r}
                schema_version = {legacy.stream()["schema_version"]!r}""",
        "text",
        caption="the same schema id, two envelopes",
    )

    ctx.say(
        "A legacy stream is **never silently upgraded**. If it were, events that "
        "carry no occurrence identity would acquire an implied one, and the replay "
        "fingerprint's exclusion set — which depends on the mode — would be "
        "computed against fields that were never recorded. The mode is chosen at "
        "construction and is part of the stream."
    )

    # -------------------------------------------------------------- resume
    ctx.section("Resume returns cumulative evidence, not a delta")

    prior = recorder.stream()
    resumed = EvidenceRecorder.resume(az, eval_ctx, prior, producer_id="nornyx-lab.occ")
    resumed.record_occurrence_decision(
        decision,
        mission_id="mission.briefing",
        occurrence=RuntimeOccurrence(operation_id="op.search", occurrence_id="occ.3", attempt=1),
    )
    ctx.say(
        f"Prior stream: **{len(prior['events'])} events**. After resume and one "
        f"more decision: **{len(resumed.stream()['events'])} events** — the whole "
        "history, not the increment."
    )
    ctx.record("resumed_count", len(resumed.stream()["events"]))

    ctx.say(
        "Differential chunks would be the cheaper contract and the wrong one: a "
        "verifier would have to reassemble them in the right order and trust that "
        "no chunk was dropped. Cumulative evidence makes a gap **visible in the "
        "artifact you are already checking**."
    )

    # --------------------------------------------------------- the artifacts
    ctx.section("What the generator actually produces")

    artifacts = sorted(p.name for p in (ATLAS / "control_artifacts").iterdir() if p.is_file())
    ctx.say(f"**{len(artifacts)} artifacts**, and the complete list matters:")
    for name in artifacts:
        ctx.note(name)

    ctx.say(
        "An incomplete published list is itself a governance hazard: a reviewer who "
        "believes there are eight artifacts will not notice that the ninth — the "
        "one describing the protocol boundary — was never reviewed."
    )

    ctx.concept(
        "declarations cannot smuggle execution",
        """
The generator scans its own output for forbidden content. A contract cannot
declare a shell command, an endpoint, or a credential and have it appear in a
generated artifact, because those fields are **structurally unrepresentable** —
not merely discouraged by convention.

That is what makes a generated artifact safe to hand to an automated consumer:
the worst a hostile contract can do is describe a boundary badly, not ship a
payload.
""",
    )

    # ------------------------------------------------------------ drift gate
    ctx.section("The drift gate, end to end")

    scratch = ctx.dir / "fresh"
    shutil.rmtree(scratch, ignore_errors=True)
    ctx.cli(generate(ATLAS / "network.nyx", scratch, cwd=ATLAS), show_output=False)

    committed = {
        p.name: p.read_bytes() for p in (ATLAS / "control_artifacts").iterdir() if p.is_file()
    }
    fresh = {p.name: p.read_bytes() for p in scratch.iterdir() if p.is_file()}
    identical = committed == fresh
    ctx.record("drift_clean", identical)

    ctx.code(
        f"""committed artifacts : {len(committed)}
freshly generated   : {len(fresh)}
byte-identical      : {identical}""",
        "text",
        caption="regenerate, then byte-compare",
    )

    # Now introduce drift the way a real engineer would: edit a generated file.
    victim = scratch / sorted(fresh)[0]
    victim.write_bytes(victim.read_bytes() + b"\n")
    drifted = {p.name: p.read_bytes() for p in scratch.iterdir() if p.is_file()}
    ctx.record("drift_detected", drifted != committed)
    shutil.rmtree(scratch, ignore_errors=True)

    ctx.verdict(
        identical and drifted != committed,
        "Clean tree compares equal; a single appended newline does not. That is "
        "the entire gate — and it only works because generation is byte-deterministic.",
    )

    ctx.say(
        """
Two drift gates exist and they have different scopes and audiences:

| gate | scope | audience |
|---|---|---|
| `nornyx drift` | the full generated directory, byte for byte | CI, blocking |
| `agentic-network lock-check` | artifacts against the lock's digests | CI **and** the authorizer's load path |

The second is the stronger one, because it runs again every time an authorizer
is constructed — not only in the pipeline.
"""
    )

    ctx.say(
        "Diagnostic **codes** and **exit codes** are both public interfaces. A "
        "pipeline gates on `AN_LOCK_ARTIFACT_MISMATCH`, not on grepping the word "
        "'mismatch' out of a message that a future release may reword."
    )
    ctx.cli(nornyx("check", "network.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS), show_output=False)

    ctx.boundary(
        """
**A clean drift gate proves the committed artifacts match the contract.**

It does not prove the running system loaded them, that the artifacts are
correct, or that anything at run time consulted them. Byte-equality is a
statement about two directories, and nothing more.
"""
    )

    ctx.tryit(
        """
1. Record a fourth event with `occurrence_id="occ.1"` and `attempt=1` — a
   duplicate. Validate the stream. Which rule catches it?
2. Try `attempt=5` on a fresh occurrence. Which rule catches *that*, and why is
   contiguity worth enforcing when a real framework's counter might legitimately
   skip?
"""
    )
