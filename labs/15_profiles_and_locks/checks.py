"""Concept checks for Lab 15.

Every test that breaks the tree restores it in a `finally`. A lab that leaves
the repository broken after one failure is a lab nobody finishes.
"""

from __future__ import annotations

import json

from nornyx_lab.constants import LAB_AS_OF
from nornyx_lab.contract import lock_check, nornyx, shared_contract

ATLAS = shared_contract("atlas")
LOCK = ATLAS / "nornyx.agentic_network.lock"
ARTIFACTS = ATLAS / "control_artifacts"


def _verify():
    return lock_check(ATLAS / "network.nyx", LOCK, ARTIFACTS, cwd=ATLAS)


def test_the_profile_is_selectable_and_inspectable():
    listing = nornyx("profiles", "list")
    assert listing.ok
    assert "agentic_network" in listing.stdout

    detail = nornyx("profiles", "inspect", "agentic_network")
    assert detail.ok


def test_the_profile_pulls_in_modules_the_contract_never_names():
    contract_text = (ATLAS / "network.nyx").read_text(encoding="utf-8")
    assert "human_approval" not in contract_text, "the contract does not select modules"

    explained = nornyx("governance", "explain", "network.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS)
    assert "nornyx.builtin.module.human_approval" in explained.stdout, (
        "but the module is in force anyway — that is what a profile does"
    )


def test_a_deleted_artifact_breaks_verification():
    victim = ARTIFACTS / "trust_zone_map.json"
    original = victim.read_bytes()
    try:
        victim.unlink()
        assert not _verify().ok
    finally:
        victim.write_bytes(original)
    assert _verify().ok


def test_an_edited_artifact_breaks_verification():
    victim = ARTIFACTS / "trust_zone_map.json"
    original = victim.read_bytes()
    tampered = original.replace(b"governed_local", b"public", 1)
    assert tampered != original, "fixture changed; update this check"
    try:
        victim.write_bytes(tampered)
        result = _verify()
        assert not result.ok
        assert result.codes(), "the failure must be diagnosable"
    finally:
        victim.write_bytes(original)
    assert _verify().ok


def test_a_lock_bound_to_another_revision_is_rejected():
    original = LOCK.read_bytes()
    corrupt = json.loads(original)
    corrupt["subject_revision"] = "git:" + "0" * 40
    try:
        LOCK.write_text(json.dumps(corrupt, indent=2), encoding="utf-8")
        assert not _verify().ok
    finally:
        LOCK.write_bytes(original)
    assert _verify().ok


def test_a_stale_lock_stops_the_authorizer_from_loading():
    """The lock is not advisory: it gates construction of the decision engine."""
    from nornyx.agentic import AuthorizerLoadError, load_authorizer

    original = LOCK.read_bytes()
    corrupt = json.loads(original)
    corrupt["subject_revision"] = "git:" + "0" * 40
    try:
        LOCK.write_text(json.dumps(corrupt, indent=2), encoding="utf-8")
        try:
            load_authorizer(ATLAS / "network.nyx", LOCK, validation_as_of=LAB_AS_OF)
        except AuthorizerLoadError as exc:
            assert exc.code.value in {"LOCK_STALE", "LOCK_INVALID"}
        else:
            raise AssertionError("a stale lock must not yield a usable authorizer")
    finally:
        LOCK.write_bytes(original)
    assert _verify().ok


def test_the_two_locks_are_different_controls():
    """profiles lock ≠ agentic-network lock. They answer different questions."""
    assert (ATLAS / "nornyx.profiles.lock").is_file()
    assert LOCK.is_file()
    assert (ATLAS / "nornyx.profiles.lock").read_bytes() != LOCK.read_bytes()
