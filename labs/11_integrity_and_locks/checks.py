"""Concept checks for Lab 11.

The tamper test restores the artifact in a `finally`. If it did not, one failed
run would leave the repository's contracts broken for every later lab.
"""

from __future__ import annotations

import json

from nornyx.agentic import (
    CapabilityRequest,
    EvaluationContext,
    EvidenceRecorder,
    contract_digest,
)
from nornyx.parser import load_nyx

from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION
from nornyx_lab.contract import authorizer_for, content_hash, lock_check, shared_contract

ATLAS = shared_contract("atlas")
LOCK = ATLAS / "nornyx.agentic_network.lock"
ARTIFACTS = ATLAS / "control_artifacts"
ID = "identity.research_assistant"


def _lock_check():
    return lock_check(ATLAS / "network.nyx", LOCK, ARTIFACTS, cwd=ATLAS)


def test_the_committed_tree_verifies_out_of_the_box():
    """A learner who clones this repo starts from a verifying state."""
    assert _lock_check().ok


def test_the_contract_digest_is_stable_and_content_addressed():
    document = load_nyx(ATLAS / "network.nyx")
    first = contract_digest(document)
    second = contract_digest(load_nyx(ATLAS / "network.nyx"))
    assert first == second
    assert first.startswith("sha256:")


def test_tampering_with_a_generated_artifact_breaks_the_lock():
    target = ARTIFACTS / "capability_matrix.json"
    original = target.read_bytes()
    before = content_hash(target)

    tampered = original.replace(b"high", b"low", 1)
    assert tampered != original, "fixture no longer contains the token being flipped"

    try:
        target.write_bytes(tampered)
        assert content_hash(target) != before
        result = _lock_check()
        assert not result.ok, "a modified artifact must not verify against the lock"
        assert result.codes(), "the failure must be diagnosable, not just non-zero"
    finally:
        target.write_bytes(original)

    assert _lock_check().ok, "restoring the bytes must restore verification"


def test_generation_is_byte_deterministic():
    """Without this, the tamper check above would be a coin flip."""
    from nornyx_lab.contract import generate

    scratch = ATLAS / ".determinism-probe"
    try:
        assert generate(ATLAS / "network.nyx", scratch, cwd=ATLAS).ok
        first = {p.name: p.read_bytes() for p in scratch.rglob("*") if p.is_file()}
        assert generate(ATLAS / "network.nyx", scratch, cwd=ATLAS).ok
        second = {p.name: p.read_bytes() for p in scratch.rglob("*") if p.is_file()}
        assert first == second
    finally:
        import shutil

        shutil.rmtree(scratch, ignore_errors=True)


def test_the_lock_binds_several_things_at_once():
    payload = json.loads(LOCK.read_text(encoding="utf-8"))
    text = json.dumps(payload)
    for expected in ("contract", "artifact", "revision"):
        assert expected in text, f"the lock should bind something about {expected}"


def test_sequences_are_contiguous_and_monotonic():
    az = authorizer_for(ATLAS)
    ctx = EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)
    rec = EvidenceRecorder(az, ctx, producer_id="nornyx-lab.integrity")
    for _ in range(4):
        rec.record_decision(
            az.evaluate(CapabilityRequest(ID, "search_web"), context=ctx),
            mission_id="mission.ordering",
        )

    sequences = [e["sequence"] for e in rec.stream()["events"]]
    assert sequences == sorted(sequences), "monotonic: rules out reordering"
    assert sequences == list(range(1, len(sequences) + 1)), "contiguous: rules out drops"


def test_missions_are_sequenced_independently():
    """Two missions do not share a counter, so neither can hide the other's gap."""
    az = authorizer_for(ATLAS)
    ctx = EvaluationContext(decision_at=LAB_AS_OF, observed_subject_revision=LAB_SUBJECT_REVISION)
    rec = EvidenceRecorder(az, ctx, producer_id="nornyx-lab.integrity")
    for mission in ("mission.a", "mission.b"):
        rec.record_decision(
            az.evaluate(CapabilityRequest(ID, "search_web"), context=ctx), mission_id=mission
        )

    by_mission: dict[str, list[int]] = {}
    for event in rec.stream()["events"]:
        by_mission.setdefault(event["mission_id"], []).append(event["sequence"])

    assert len(by_mission) == 2
    for sequences in by_mission.values():
        assert sequences == list(range(1, len(sequences) + 1))
