"""Concept checks for Lab 21 — the gate set, run against this repository."""

from __future__ import annotations

import shutil

from nornyx_lab.constants import LAB_AS_OF
from nornyx_lab.contract import generate, lock_check, nornyx, shared_contract
from nornyx_lab.engine import all_labs, repo_root

ATLAS = shared_contract("atlas")
LEDGER = shared_contract("ledger")


def test_gate_check_passes_for_every_contract():
    for contract in (ATLAS, LEDGER):
        result = nornyx("check", "network.nyx", "--as-of", LAB_AS_OF, cwd=contract)
        assert result.ok, f"{contract.name}: {result.stdout}{result.stderr}"
        assert result.returncode == 0


def test_gate_lock_verification_passes_for_every_contract():
    for contract in (ATLAS, LEDGER):
        result = lock_check(
            contract / "network.nyx",
            contract / "nornyx.agentic_network.lock",
            contract / "control_artifacts",
            cwd=contract,
        )
        assert result.ok, f"{contract.name}: {result.stdout}{result.stderr}"


def test_gate_drift_is_clean_for_every_contract(tmp_path):
    for contract in (ATLAS, LEDGER):
        fresh = tmp_path / contract.name
        assert generate(contract / "network.nyx", fresh, cwd=contract).ok

        committed = {
            p.name: p.read_bytes()
            for p in (contract / "control_artifacts").iterdir()
            if p.is_file()
        }
        regenerated = {p.name: p.read_bytes() for p in fresh.iterdir() if p.is_file()}
        assert committed == regenerated, f"{contract.name} generated artifacts have drifted"
        shutil.rmtree(fresh, ignore_errors=True)


def test_a_failing_gate_returns_a_specific_diagnostic_code(tmp_path):
    """Gates must be specific, or teams turn them off."""
    probe = ATLAS / "gate_probe.nyx"
    original = (ATLAS / "network.nyx").read_text(encoding="utf-8")
    probe.write_text(original.replace("risk: high", "risk: nonsense", 1), encoding="utf-8")
    try:
        result = nornyx("check", "gate_probe.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS)
        assert not result.ok
        assert result.codes(), "a gate that cannot name its failure cannot be routed"
    finally:
        probe.unlink(missing_ok=True)


def test_the_repository_ships_a_ci_workflow_running_these_gates():
    workflow = repo_root() / ".github" / "workflows" / "ci.yml"
    assert workflow.is_file(), "the gate set must be wired, not just described"

    text = workflow.read_text(encoding="utf-8")
    for expected in ("build_contracts.py --verify", "pytest", "conformance"):
        assert expected in text, f"CI does not run {expected}"


def test_ci_requires_both_framework_extras_so_nothing_skips():
    """Zero-skip detection: a silent skip is a governance failure."""
    text = (repo_root() / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "--require crewai" in text
    assert "--require langgraph" in text


def test_every_lab_declares_the_chapters_it_covers():
    """Traceability is a gate too: an untraceable lab is an unreviewable one."""
    for meta in all_labs():
        assert meta.chapters, f"lab {meta.id} declares no chapters"
        assert meta.objectives, f"lab {meta.id} declares no objectives"
        assert meta.concepts, f"lab {meta.id} declares no concepts"
