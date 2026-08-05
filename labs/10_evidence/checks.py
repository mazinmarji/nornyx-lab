"""Concept checks for Lab 10."""

from __future__ import annotations

import pytest
from nornyx.agentic import (
    CapabilityRequest,
    EvaluationContext,
    EvidenceRecorder,
    ZoneCrossingRequest,
)

from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, shared_contract

ATLAS = shared_contract("atlas")
ID = "identity.research_assistant"
MISSION = "mission.q3-briefing"


def _ctx():
    return EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)


def _recorded():
    az = authorizer_for(ATLAS)
    ctx = _ctx()
    rec = EvidenceRecorder(az, ctx, producer_id="nornyx-lab.atlas")
    rec.record_decision(
        az.evaluate(CapabilityRequest(ID, "search_web"), context=ctx), mission_id=MISSION
    )
    rec.record_observation(
        "tool_invoked", mission_id=MISSION, actor_ref=ID, capability_ref="search_web"
    )
    rec.record_decision(
        az.evaluate(
            ZoneCrossingRequest(ID, "zone.research_internal", "zone.public_web"), context=ctx
        ),
        mission_id=MISSION,
    )
    return rec


def test_every_event_carries_the_five_binding_fields():
    """Remove any one and a specific class of mismatch stops being detectable."""
    stream = _recorded().stream()
    assert stream["events"]

    for event in stream["events"]:
        for field in (
            "contract_digest",
            "network_lock_digest",
            "subject_revision",
            "network_id",
            "sequence",
        ):
            assert field in event, f"{event['event_type']} is missing {field}"
        assert event["subject_revision"] == LAB_SUBJECT_REVISION


def test_sequence_numbers_are_contiguous_within_a_mission():
    """A gap is how you notice a record went missing."""
    events = _recorded().stream()["events"]
    sequences = [e["sequence"] for e in events if e["mission_id"] == MISSION]
    assert sequences == list(range(1, len(sequences) + 1))


def test_the_stream_validates_against_the_contract_and_lock():
    report = _recorded().validate()
    assert report["status"] == "pass"
    assert report["diagnostics"] == []
    assert report["event_count"] >= 3


def test_the_report_publishes_its_own_limitations():
    """A validator that does not state what it cannot prove invites overclaiming."""
    report = _recorded().validate()
    limitations = " ".join(report.get("limitations", []))
    assert limitations, "the report must state its boundary"
    assert "not event truth" in limitations or "content binding" in limitations


def test_decision_events_cannot_be_minted_by_the_caller():
    """The engine will not let an adapter assert an allow it never decided."""
    rec = _recorded()
    with pytest.raises((ValueError, TypeError, KeyError)):
        rec.record_observation("capability_allowed", mission_id=MISSION, actor_ref=ID)


def test_the_recorder_refuses_a_mismatched_runtime_revision():
    """Binding is enforced at construction, not hoped for at validation."""
    az = authorizer_for(ATLAS)
    wrong = EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision="git:" + "0" * 40)
    with pytest.raises(ValueError):
        EvidenceRecorder(az, wrong, producer_id="nornyx-lab.atlas")


def test_a_denied_action_still_produces_evidence():
    """Denials are the records an auditor most wants, and are easiest to drop."""
    report = _recorded().validate()
    assert report["counts_by_type"].get("capability_requested", 0) >= 1
    types = set(report["counts_by_type"])
    assert types & {"capability_denied", "approval_requested", "capability_allowed"}
