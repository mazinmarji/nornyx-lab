"""Concept checks for Lab 17."""

from __future__ import annotations

import shutil

from nornyx.agentic import (
    CapabilityRequest,
    EvaluationContext,
    EvidenceRecorder,
    RuntimeOccurrence,
)

from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, generate, shared_contract

ATLAS = shared_contract("atlas")
ID = "identity.research_assistant"
MISSION = "mission.briefing"


def _ctx():
    return EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)


def _occurrence_recorder():
    az = authorizer_for(ATLAS)
    ctx = _ctx()
    rec = EvidenceRecorder.for_occurrences(az, ctx, producer_id="nornyx-lab.occ")
    return az, ctx, rec


def test_explicit_mode_carries_execution_identity():
    az, ctx, rec = _occurrence_recorder()
    rec.record_occurrence_decision(
        az.evaluate(CapabilityRequest(ID, "search_web"), context=ctx),
        mission_id=MISSION,
        occurrence=RuntimeOccurrence(operation_id="op.a", occurrence_id="occ.1", attempt=1),
    )
    event = rec.stream()["events"][0]

    assert rec.stream()["occurrence_mode"] == "explicit"
    assert event["occurrence"] == {
        "operation_id": "op.a",
        "occurrence_id": "occ.1",
        "attempt": 1,
    }


def test_legacy_mode_is_a_different_envelope_of_the_same_schema():
    az = authorizer_for(ATLAS)
    ctx = _ctx()
    legacy = EvidenceRecorder(az, ctx, producer_id="nornyx-lab.legacy")
    legacy.record_decision(
        az.evaluate(CapabilityRequest(ID, "search_web"), context=ctx), mission_id=MISSION
    )
    explicit = EvidenceRecorder.for_occurrences(az, ctx, producer_id="nornyx-lab.occ")

    assert legacy.stream()["schema"] == explicit.stream()["schema"]
    assert legacy.stream()["occurrence_mode"] != explicit.stream()["occurrence_mode"]


def test_retry_and_repeated_work_are_distinguishable():
    """The whole reason execution identity exists."""
    az, ctx, rec = _occurrence_recorder()
    decision = az.evaluate(CapabilityRequest(ID, "search_web"), context=ctx)

    for attempt in (1, 2):  # a retry
        rec.record_occurrence_decision(
            decision,
            mission_id=MISSION,
            occurrence=RuntimeOccurrence("op.a", "occ.1", attempt),
        )
    rec.record_occurrence_decision(  # repeated work
        decision, mission_id=MISSION, occurrence=RuntimeOccurrence("op.a", "occ.2", 1)
    )

    occurrences = {e["occurrence"]["occurrence_id"] for e in rec.stream()["events"]}
    assert occurrences == {"occ.1", "occ.2"}
    assert (
        rec.max_recorded_attempt(mission_id=MISSION, operation_id="op.a", occurrence_id="occ.1")
        == 2
    )
    assert (
        rec.max_recorded_attempt(mission_id=MISSION, operation_id="op.a", occurrence_id="occ.2")
        == 1
    )


def test_the_occurrence_stream_validates():
    az, ctx, rec = _occurrence_recorder()
    rec.record_occurrence_decision(
        az.evaluate(CapabilityRequest(ID, "search_web"), context=ctx),
        mission_id=MISSION,
        occurrence=RuntimeOccurrence("op.a", "occ.1", 1),
    )
    report = rec.validate()
    assert report["status"] == "pass"
    assert report["diagnostics"] == []


def test_resume_returns_the_whole_history_not_a_delta():
    az, ctx, rec = _occurrence_recorder()
    decision = az.evaluate(CapabilityRequest(ID, "search_web"), context=ctx)
    rec.record_occurrence_decision(
        decision, mission_id=MISSION, occurrence=RuntimeOccurrence("op.a", "occ.1", 1)
    )
    prior = rec.stream()
    before = len(prior["events"])

    resumed = EvidenceRecorder.resume(az, ctx, prior, producer_id="nornyx-lab.occ")
    resumed.record_occurrence_decision(
        decision, mission_id=MISSION, occurrence=RuntimeOccurrence("op.a", "occ.2", 1)
    )

    assert len(resumed.stream()["events"]) > before
    assert resumed.validate()["status"] == "pass"


def test_resume_rejects_a_stream_from_another_producer():
    """Cumulative evidence is only safe if the prefix is genuinely yours."""
    az, ctx, rec = _occurrence_recorder()
    rec.record_occurrence_decision(
        az.evaluate(CapabilityRequest(ID, "search_web"), context=ctx),
        mission_id=MISSION,
        occurrence=RuntimeOccurrence("op.a", "occ.1", 1),
    )
    try:
        EvidenceRecorder.resume(az, ctx, rec.stream(), producer_id="someone.else")
    except Exception:
        return
    raise AssertionError("resuming another producer's stream must not be permitted")


def test_the_committed_artifacts_match_a_fresh_generation(tmp_path):
    """The drift gate, run for real."""
    scratch = tmp_path / "fresh"
    assert generate(ATLAS / "network.nyx", scratch, cwd=ATLAS).ok

    committed = {
        p.name: p.read_bytes() for p in (ATLAS / "control_artifacts").iterdir() if p.is_file()
    }
    fresh = {p.name: p.read_bytes() for p in scratch.iterdir() if p.is_file()}

    assert committed == fresh, "the committed generated artifacts have drifted"
    shutil.rmtree(scratch, ignore_errors=True)


def test_a_one_byte_edit_is_detected(tmp_path):
    scratch = tmp_path / "drifted"
    assert generate(ATLAS / "network.nyx", scratch, cwd=ATLAS).ok

    victim = sorted(p for p in scratch.iterdir() if p.is_file())[0]
    victim.write_bytes(victim.read_bytes() + b"\n")

    committed = {
        p.name: p.read_bytes() for p in (ATLAS / "control_artifacts").iterdir() if p.is_file()
    }
    drifted = {p.name: p.read_bytes() for p in scratch.iterdir() if p.is_file()}
    assert drifted != committed


def test_generated_artifacts_carry_no_executable_content():
    """Declarations cannot smuggle execution."""
    for path in (ATLAS / "control_artifacts").iterdir():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for forbidden in ("#!/bin/", "subprocess", "os.system", "eval(", "curl http"):
            assert forbidden not in text, f"{path.name} contains {forbidden!r}"
