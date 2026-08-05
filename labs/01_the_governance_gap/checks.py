"""Concept checks for Lab 01."""

from __future__ import annotations

from pathlib import Path

from nornyx_lab import northstar
from nornyx_lab.contract import nornyx
from nornyx_lab.ledger import Ledger

LAB = Path(__file__).parent
CONTRACT = LAB / "contract" / "delivery.nyx"


def test_the_scattered_controls_actually_contradict():
    """Not a rhetorical claim — the two files state opposite rules."""
    assert "Tests are optional" in northstar.AGENTS_MD
    assert "tests_required: true" in northstar.POLICY_YAML
    # Nothing in either file references the other. That is the gap.
    assert "policy.yaml" not in northstar.AGENTS_MD
    assert "AGENTS.md" not in northstar.POLICY_YAML


def test_an_agent_following_agents_md_merges_without_tests():
    ledger = Ledger("ungoverned")
    northstar.merge_pull_request(ledger, "PR-77", tests_passed=False)

    assert ledger.completions("merge_pull_request") == 1
    assert ledger.entries[0].fields["tests_passed"] is False


def test_the_contract_is_valid():
    """If this fails, the lesson is broken, not your understanding."""
    result = nornyx("check", str(CONTRACT))
    assert result.ok, result.stdout + result.stderr


def test_generation_produces_the_scattered_artifacts_from_one_source():
    """The four audiences are now served by projections of a single file."""
    out = LAB / "generated"
    result = nornyx("generate", str(CONTRACT), "--out", str(out))
    assert result.ok, result.stdout + result.stderr

    produced = {p.name for p in out.rglob("*") if p.is_file()}
    assert produced, "generate wrote nothing"
    assert "AGENTS.md" in produced, f"expected AGENTS.md among {sorted(produced)}"


def test_generation_is_byte_deterministic():
    """Determinism is what makes a drift gate possible at all (Ch. 21).

    If generating twice produced different bytes, 'regenerate and compare' would
    fail at random and every team would delete the gate within a month.
    """
    first = LAB / "generated"
    second = LAB / ".generated-again"

    assert nornyx("generate", str(CONTRACT), "--out", str(first)).ok
    assert nornyx("generate", str(CONTRACT), "--out", str(second)).ok

    for path in sorted(p for p in first.rglob("*") if p.is_file()):
        mirror = second / path.relative_to(first)
        assert mirror.is_file(), f"{path.name} missing from the second generation"
        assert mirror.read_bytes() == path.read_bytes(), f"{path.name} is not deterministic"


def test_generated_artifacts_are_derived_not_authoritative():
    """Editing a generated file is a bug the next generate silently corrects."""
    out = LAB / "generated"
    agents = out / "AGENTS.md"
    assert nornyx("generate", str(CONTRACT), "--out", str(out)).ok

    original = agents.read_text(encoding="utf-8")
    agents.write_text(original + "\nThe agent may skip tests on Fridays.\n", encoding="utf-8")
    assert "Fridays" in agents.read_text(encoding="utf-8")

    assert nornyx("generate", str(CONTRACT), "--out", str(out)).ok
    assert "Fridays" not in agents.read_text(encoding="utf-8"), (
        "a hand edit to a derived artifact must not survive regeneration"
    )
