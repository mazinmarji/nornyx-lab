"""Concept checks for Lab 14.

These pin the *teaching claim*: that the diagnostics fall in three groups and
that fixing each group in order strictly reduces the count to zero.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from nornyx_lab.constants import LAB_AS_OF
from nornyx_lab.contract import nornyx, seal_evidence, shared_contract

LAB = Path(__file__).parent
STAGES = LAB / "stages"


def _check_stage(stage: str, tmp_path: Path, *, seal: bool = False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    shutil.copy(STAGES / f"{stage}.nyx", tmp_path / "network.nyx")
    shutil.copytree(
        shared_contract("atlas") / "governance_evidence",
        tmp_path / "governance_evidence",
        dirs_exist_ok=True,
    )
    if seal:
        seal_evidence(tmp_path / "network.nyx")
    return nornyx("check", "network.nyx", "--as-of", LAB_AS_OF, cwd=tmp_path)


def test_the_starter_fails_with_the_three_families(tmp_path):
    result = _check_stage("starter", tmp_path)
    assert not result.ok
    codes = set(result.codes())

    # 1. missing evidence block
    assert {"GOVERNANCE_REQUIRED_BLOCK_MISSING"} & codes, codes
    # 2. names the profile fixes
    assert {"AN_APPROVAL_DECLARATION_MISSING", "AN_RELATION_APPROVER_NOT_HUMAN"} & codes, codes


def test_adding_evidence_strictly_reduces_the_count(tmp_path):
    starter = _check_stage("starter", tmp_path / "a")
    with_evidence = _check_stage("with_evidence", tmp_path / "b")

    assert len(with_evidence.codes()) < len(starter.codes())
    assert "GOVERNANCE_REQUIRED_BLOCK_MISSING" not in with_evidence.codes()


def test_using_the_profiles_names_reduces_it_further(tmp_path):
    with_evidence = _check_stage("with_evidence", tmp_path / "b")
    with_names = _check_stage("with_profile_names", tmp_path / "c")

    assert len(with_names.codes()) < len(with_evidence.codes())
    for code in ("AN_APPROVAL_DECLARATION_MISSING", "AN_APPROVAL_DECLARED_ROLE_UNAUTHORIZED"):
        assert code not in with_names.codes()


def test_the_profile_fixes_the_approval_name_and_role():
    """You may not choose these. That is a superior layer, not a style guide."""
    wrong = (STAGES / "with_evidence.nyx").read_text(encoding="utf-8")
    right = (STAGES / "with_profile_names.nyx").read_text(encoding="utf-8")

    assert "publication_authority" in wrong
    assert "agentic_network_authority" in right
    assert "research_governance_owner" in wrong
    assert "network_governance_owner" in right


def test_unsealed_digests_are_the_last_thing_standing(tmp_path):
    """Everything else is right; the evidence bindings still do not match."""
    unsealed = _check_stage("sealed", tmp_path / "d", seal=False)
    assert not unsealed.ok
    assert any("HASH" in c or "DIGEST" in c or "EVIDENCE" in c for c in unsealed.codes()), (
        unsealed.codes()
    )


def test_sealing_the_digests_produces_a_valid_contract(tmp_path):
    sealed = _check_stage("sealed", tmp_path / "e", seal=True)
    assert sealed.ok, sealed.stdout + sealed.stderr


def test_seal_actually_rewrites_the_digests(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    shutil.copy(STAGES / "sealed.nyx", tmp_path / "network.nyx")
    shutil.copytree(
        shared_contract("atlas") / "governance_evidence",
        tmp_path / "governance_evidence",
        dirs_exist_ok=True,
    )
    changes = seal_evidence(tmp_path / "network.nyx")
    assert len(changes) == 3, f"expected three evidence records resealed, got {changes}"
    for _artifact, old, new in changes:
        assert old != new
        assert new.startswith("sha256:")


def test_the_contract_declares_its_non_goals():
    """A contract that has not said what it is not has not decided what it is."""
    text = (STAGES / "sealed.nyx").read_text(encoding="utf-8")
    assert "non_goals:" in text
    for non_goal in ("tool execution", "model execution", "automatic approvals"):
        assert non_goal in text
