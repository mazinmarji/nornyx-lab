"""Repository-level invariants.

These do not teach anything. They stop the repository from quietly breaking the
promises its README makes — including the coverage claim, which is the one a
reader is least able to check for themselves.
"""

from __future__ import annotations

import re
import subprocess
import sys

import pytest

from nornyx_lab.constants import PINNED_ADAPTERS, PINNED_NORNYX
from nornyx_lab.contract import nornyx
from nornyx_lab.engine import all_labs, repo_root

ROOT = repo_root()
TOTAL_CHAPTERS = 41


# ------------------------------------------------------------------ structure
def test_there_are_twenty_five_labs_numbered_without_gaps():
    labs = all_labs()
    assert len(labs) == 25
    assert [m.id for m in labs] == [f"{n:02d}" for n in range(25)]


@pytest.mark.parametrize("meta", all_labs(), ids=lambda m: m.id)
def test_every_lab_has_its_four_files(meta):
    for name in ("lab.toml", "lab.py", "checks.py", "README.md"):
        assert (meta.path / name).is_file(), f"lab {meta.id} is missing {name}"


@pytest.mark.parametrize("meta", all_labs(), ids=lambda m: m.id)
def test_every_lab_exposes_a_run_function(meta):
    source = (meta.path / "lab.py").read_text(encoding="utf-8")
    assert re.search(r"^def run\(ctx: LabContext\) -> None:", source, re.M), (
        f"lab {meta.id} does not expose run(ctx)"
    )


@pytest.mark.parametrize("meta", all_labs(), ids=lambda m: m.id)
def test_every_lab_declares_prerequisites_that_exist(meta):
    known = {m.id for m in all_labs()}
    for required in meta.requires:
        assert required in known, f"lab {meta.id} requires unknown lab {required}"


# ------------------------------------------------------------------- coverage
def test_every_textbook_chapter_maps_to_a_lab():
    """The README's headline claim, verified.

    'Every chapter has a lab' is exactly the kind of sentence this book warns
    about — easy to write, hard for a reader to check. So it is a test.
    """
    covered = {
        int(chapter) for meta in all_labs() for chapter in re.findall(r"Ch\. (\d+)", meta.chapters)
    }
    missing = sorted(set(range(1, TOTAL_CHAPTERS + 1)) - covered)
    assert not missing, f"chapters with no lab: {missing}"


def test_the_generated_docs_are_current():
    """docs/ and the lab READMEs are derived. Regenerate and byte-compare.

    This is Lab 01's lesson applied to this repository: a derived artifact that
    can drift from its source is a governance hazard, however small.
    """
    before = {
        path: path.read_bytes()
        for path in [
            *(m.path / "README.md" for m in all_labs()),
            ROOT / "docs" / "COVERAGE.md",
            ROOT / "docs" / "CONCEPTS.md",
        ]
    }
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_docs.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    drifted = [str(p.relative_to(ROOT)) for p, data in before.items() if p.read_bytes() != data]
    assert not drifted, f"stale generated docs — run `python scripts/build_docs.py`: {drifted}"


# ------------------------------------------------------------------- contracts
def test_the_committed_contracts_have_not_drifted():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_contracts.py"), "--verify"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize("name", ["atlas", "ledger"])
def test_each_contract_ships_its_generated_outputs(name):
    contract = ROOT / "contracts" / name
    assert (contract / "network.nyx").is_file()
    assert (contract / "nornyx.agentic_network.lock").is_file()
    assert (contract / "nornyx.profiles.lock").is_file()
    assert list((contract / "control_artifacts").glob("*.json"))
    assert list((contract / "governance_evidence").glob("*.json"))


# --------------------------------------------------------------------- pinning
def test_the_toolchain_is_pinned_exactly():
    """A floating range would let a release change a diagnostic code and
    silently invalidate a lesson."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'"nornyx=={PINNED_NORNYX}"' in text
    assert f'"nornyx-agentic-adapters=={PINNED_ADAPTERS}"' in text


def test_the_installed_versions_match_the_pins():
    import nornyx
    import nornyx_agentic_adapters

    assert nornyx.__version__ == PINNED_NORNYX
    assert nornyx_agentic_adapters.__version__ == PINNED_ADAPTERS


def test_the_cli_is_runnable():
    result = nornyx("--version")
    assert result.ok
    assert PINNED_NORNYX in result.stdout


# ---------------------------------------------------------------- honest README
def test_the_readme_states_the_tier_and_the_bypass():
    """The repository must not overclaim about itself."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Tier 2" in readme
    assert "not governed by Nornyx" in readme, (
        "the README must say that nornyx-lab does not self-apply the control"
    )


def test_no_lab_claims_tier_3():
    for meta in all_labs():
        source = (meta.path / "lab.py").read_text(encoding="utf-8")
        for phrase in ("we are Tier 3", "achieves Tier 3", "is Tier 3"):
            assert phrase not in source, f"lab {meta.id} claims Tier 3"
