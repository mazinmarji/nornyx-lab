"""Repository-level invariants.

These do not teach anything. They stop the repository from quietly breaking the
promises its README makes — including the coverage claim, which is the one a
reader is least able to check for themselves.
"""

from __future__ import annotations

import os
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


def test_no_workflow_uses_a_step_only_context_outside_a_step():
    """A whole-workflow rejection that produces no logs at all.

    `runner`, `steps`, `job`, and `matrix` (outside `strategy`) are only
    available inside a step. Using one in a job-level `env:` block makes GitHub
    refuse the ENTIRE file before scheduling anything — a 0-second run, zero
    jobs, no annotations in the API, and nothing to debug from.

    Codex's workflow had `NORNYX_ACADEMY_DB: ${{ runner.temp }}/...` in a
    job-level env block, so every CI job in this repository silently never ran.
    """
    import yaml

    step_only = ("runner.", "steps.", "job.")
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        parsed = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        for job_name, job in (parsed.get("jobs") or {}).items():
            for key, value in (job.get("env") or {}).items():
                rendered = str(value)
                for context in step_only:
                    assert context not in rendered, (
                        f"{workflow.name}: job '{job_name}' env '{key}' uses "
                        f"${{{{ {context}... }}}}, which is unavailable at job level "
                        f"and rejects the whole workflow. Export it from a step "
                        f"into $GITHUB_ENV instead."
                    )


def test_the_lab_migration_matrix_is_current_and_has_no_gaps():
    """Every original lab must have a documented disposition.

    The generator exits non-zero if any lab lacks an academy module, an
    assessment that actually exists, or membership in a learning path — so a
    silently dropped lab fails here rather than being discovered by a learner.
    """
    generator = ROOT / "scripts" / "build_migration_matrix.py"
    matrix = ROOT / "docs" / "LAB_MIGRATION_MATRIX.md"
    assert generator.is_file()

    before = matrix.read_bytes() if matrix.is_file() else b""
    proc = subprocess.run(
        [sys.executable, str(generator)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"migration matrix has gaps:\n{proc.stdout}{proc.stderr}"
    assert matrix.read_bytes() == before, (
        "docs/LAB_MIGRATION_MATRIX.md is stale — run scripts/build_migration_matrix.py"
    )

    text = matrix.read_text(encoding="utf-8")
    for meta in all_labs():
        assert f"### Lab {meta.id} — {meta.title}" in text, f"lab {meta.id} missing from the matrix"
    assert "UNMAPPED" not in text


def test_every_lab_has_a_valid_notebook_companion():
    """The README promises one notebook per lab. Check the promise.

    Cell ids are required by nbformat 4.5+. Without them Jupyter warns that it
    will become a hard error, then generates a RANDOM id at execution time —
    which, for committed notebooks, would make regenerate-and-compare report
    drift that is not drift.
    """
    import json

    notebooks = ROOT / "notebooks"
    labs = all_labs()
    assert notebooks.is_dir(), "run `python scripts/build_notebooks.py`"

    for meta in labs:
        path = notebooks / f"{meta.slug}.ipynb"
        assert path.is_file(), f"lab {meta.id} has no notebook"

        nb = json.loads(path.read_text(encoding="utf-8"))
        assert nb["nbformat"] == 4
        assert nb["nbformat_minor"] >= 5, "cell ids need nbformat 4.5+"
        assert nb["cells"], f"{path.name} has no cells"

        ids = [cell.get("id") for cell in nb["cells"]]
        assert all(ids), f"{path.name} has a cell with no id"
        assert len(set(ids)) == len(ids), f"{path.name} has duplicate cell ids"


def test_a_lab_survives_a_legacy_console_encoding():
    """Regression: the labs print ✔, ✘, ⊘ and box drawing.

    On Windows, piped stdout gets the console code page (cp1252), and those
    purely decorative glyphs killed the run with UnicodeEncodeError three
    sections in — in CI, and for anyone doing `nornyx-lab run 00 > out.txt`.
    `nornyx_lab.ui` now forces UTF-8 on stdout/stderr at import.
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"
    proc = subprocess.run(
        [sys.executable, "-m", "nornyx_lab.cli", "run", "00"],
        cwd=str(ROOT),
        capture_output=True,
        env=env,
    )
    stderr = proc.stderr.decode("utf-8", "replace")

    assert "UnicodeEncodeError" not in stderr, stderr[-800:]
    assert proc.returncode == 0
    assert proc.stdout, "the lab produced no output at all"


def test_crewai_first_run_kill_switches_are_set_on_import():
    """A fresh CrewAI spawns a process during first-run tracing consent.

    The adapter's conformance suite runs guarded and reports `nonconformant`
    when anything spawns a process — so a clean machine failed while any
    machine that had already run CrewAI once passed. Importing
    `nornyx_lab.optional` sets the kill switches before any framework import.
    """
    import nornyx_lab.optional  # noqa: F401

    assert os.environ.get("CREWAI_TESTING") == "true"
    assert os.environ.get("CREWAI_DISABLE_TELEMETRY") == "true"
    assert os.environ.get("CREWAI_TRACING_ENABLED") == "false"
    assert os.environ.get("OTEL_SDK_DISABLED") == "true"


def test_no_lab_claims_tier_3():
    for meta in all_labs():
        source = (meta.path / "lab.py").read_text(encoding="utf-8")
        for phrase in ("we are Tier 3", "achieves Tier 3", "is Tier 3"):
            assert phrase not in source, f"lab {meta.id} claims Tier 3"


# ------------------------------------------------------ tests that actually run
def _workflow():
    import yaml

    return yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))


def _all_run_commands(job) -> str:
    return "\n".join(str(step.get("run", "")) for step in job.get("steps", []))


def test_every_feedback_test_file_is_collected_by_a_ci_job():
    """A test file that CI never collects is documentation, not a gate.

    This repository has already been bitten by exactly that. The academy
    feedback suites live under `tests/academy/`, which `backend-fast` collects
    wholesale, and the gateway lives in its own distribution that nothing else
    collects — so it needs a job of its own, and this asserts it has one.
    """

    academy_files = sorted((ROOT / "tests" / "academy").glob("test_feedback*.py"))
    assert academy_files, "the H1 academy suites are missing entirely"

    workflow = _workflow()
    jobs = workflow["jobs"]

    backend = _all_run_commands(jobs["backend-fast"])
    assert "pytest tests/academy" in backend, (
        "backend-fast no longer collects tests/academy, so the H1 feedback suites "
        "would silently stop running"
    )

    gateway_job = jobs.get("feedback-gateway")
    assert gateway_job is not None, (
        "the feedback gateway is a separate distribution; without its own CI job "
        "none of its tests execute"
    )
    assert any(
        step.get("working-directory") == "gateway" and "pytest" in str(step.get("run", ""))
        for step in gateway_job["steps"]
    ), "the feedback-gateway job does not actually run pytest in gateway/"


def test_the_feedback_gateway_tests_exist_and_are_non_empty():
    gateway_tests = sorted((ROOT / "gateway" / "tests").glob("test_*.py"))
    assert gateway_tests, "gateway/tests contains no test modules"
    for path in gateway_tests:
        assert "def test_" in path.read_text(encoding="utf-8"), f"{path.name} defines no tests"


def test_every_suite_with_a_no_skip_gate_still_has_one():
    """Silent skips are how a green run stops meaning anything.

    Each serial suite asserts zero skips from its own JUnit report. A new job
    that runs tests without that assertion can go quietly yellow forever.
    """

    jobs = _workflow()["jobs"]
    for name in (
        "backend-fast",
        "legacy-regression",
        "structured-migration",
        "feedback-gateway",
    ):
        commands = _all_run_commands(jobs[name])
        assert "pytest skipped" in commands, f"job '{name}' has no no-silent-skip gate"


def test_no_ci_job_requires_a_real_github_credential():
    """The gateway holds GitHub authority. CI must never need it to pass."""

    workflow = _workflow()
    rendered = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for job_name, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            for key, value in (step.get("env") or {}).items():
                assert "NORNYX_FEEDBACK_GITHUB_TOKEN" not in key, (
                    f"job '{job_name}' injects a feedback GitHub token"
                )
                assert "NORNYX_FEEDBACK_GITHUB_TOKEN" not in str(value)
    # `secrets.` may legitimately appear nowhere in this workflow at all.
    assert "secrets." not in rendered, (
        "CI references a repository secret; the feedback boundary is designed so no job needs one"
    )


def test_no_committed_file_carries_a_github_credential_pattern():
    import re

    pattern = re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}")
    proc = subprocess.run(
        ["git", "ls-files"], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8"
    )
    assert proc.returncode == 0, proc.stderr
    offenders = []
    for relative in proc.stdout.splitlines():
        path = ROOT / relative
        if not path.is_file() or path.suffix in {".png", ".jpg", ".ico", ".woff2"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if pattern.search(text):
            offenders.append(relative)
    assert not offenders, f"committed files contain a GitHub credential pattern: {offenders}"
