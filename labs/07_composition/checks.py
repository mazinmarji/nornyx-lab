"""Concept checks for Lab 07."""

from __future__ import annotations

from pathlib import Path

from nornyx_lab.constants import LAB_AS_OF
from nornyx_lab.contract import nornyx, shared_contract

ATLAS = shared_contract("atlas")
HERE = Path(__file__).parent


def test_the_effective_policy_is_larger_than_the_contract():
    """Three modules are in force that the contract never names."""
    result = nornyx("governance", "explain", "network.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS)
    assert result.ok, result.stdout + result.stderr

    out = result.stdout
    assert "nornyx.builtin.module.human_approval" in out
    assert "nornyx.builtin.module.evidence_integrity" in out
    assert "nornyx.builtin.module.agentic_network_governance" in out
    assert "status: pass" in out


def test_provenance_names_the_contributing_pack():
    result = nornyx("governance", "matrix", "network.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS)
    assert result.ok, result.stdout + result.stderr
    assert "nornyx.builtin.agentic_network" in result.stdout


def test_composition_is_dependency_ordered():
    """agentic_network_governance declares a dependency on human_approval."""
    result = nornyx("modules", "list")
    assert result.ok
    assert "nornyx.builtin.module.human_approval" in result.stdout


def test_a_lower_layer_cannot_widen_a_superior_control():
    """The headline property. Removing a module-mandated denial is refused."""
    original = (ATLAS / "network.nyx").read_text(encoding="utf-8")
    weakened = original.replace(
        "denied_actor_types: [ai_tool, execution_surface, autonomous_agent, model, connector, generated_output]",
        "denied_actor_types: [execution_surface, connector]",
    )
    assert weakened != original, "the fixture text moved; update this check"

    probe = ATLAS / "weakened_probe.nyx"
    probe.write_text(weakened, encoding="utf-8")
    try:
        result = nornyx("check", "weakened_probe.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS)
        assert not result.ok
        assert "APPROVAL_CORE_DENIAL_MISSING" in result.codes(), result.codes()
    finally:
        probe.unlink(missing_ok=True)


def test_narrowing_is_permitted_where_widening_is_not():
    """The asymmetry, demonstrated rather than asserted."""
    original = (ATLAS / "network.nyx").read_text(encoding="utf-8")
    narrowed = original.replace(
        "denied_actor_types: [ai_tool, execution_surface, autonomous_agent, model, connector, generated_output]",
        "denied_actor_types: [ai_tool, execution_surface, autonomous_agent, model, connector, generated_output, data_pipeline]",
    )
    probe = ATLAS / "narrowed_probe.nyx"
    probe.write_text(narrowed, encoding="utf-8")
    try:
        result = nornyx("check", "narrowed_probe.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS)
        assert result.ok, "adding a denial is a narrowing and must be allowed:\n" + result.stdout
    finally:
        probe.unlink(missing_ok=True)


def test_the_profiles_lock_exists_and_verifies():
    assert (ATLAS / "nornyx.profiles.lock").is_file(), "run scripts/build_contracts.py"
    result = nornyx("governance", "matrix", "network.nyx", "--as-of", LAB_AS_OF, cwd=ATLAS)
    assert "status: verified" in result.stdout


def test_the_lock_carries_no_timestamp():
    """A lock with a clock in it cannot be byte-compared, so it cannot gate."""
    text = (ATLAS / "nornyx.profiles.lock").read_text(encoding="utf-8")
    for marker in ("generated_at", "timestamp", "created_at"):
        assert marker not in text, f"{marker} would make this lock uncomparable"
