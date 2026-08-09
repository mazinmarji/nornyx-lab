"""Behavioural tests for the verification harness — it is *executed*, not read.

The static guards in `test_independent_verification.py` check the shape of the
script. These run it, because the four defects they cover are all cases where
the source looked right and the behaviour was not:

  - a run killed midway reported `pass`;
  - a preflight failure tore down a composition the run never started;
  - creating the log made a pristine checkout report as dirty;
  - a bare `--evidence` consumed an argument that was not there.

Docker is stubbed with a recording shim on PATH, so these need no daemon and no
network. What is under test is the harness's own control flow.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nornyx_lab.engine import repo_root

ROOT = repo_root()
SCRIPT = ROOT / "scripts" / "verify_independent_deployment.sh"

BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="the harness is a bash script")


def _stub_docker(directory: Path, *, build_sleep: int = 0, daemon: bool = True) -> Path:
    """A `docker` that records its arguments instead of doing anything.

    Enough of the surface to get the harness past its prerequisite checks, so
    the control flow under test is reached without a daemon.
    """
    bin_dir = directory / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    calls = directory / "docker-calls.txt"
    (bin_dir / "docker").write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$@" >> "{calls.as_posix()}"\n'
        'case "$1" in\n'
        '  --version) echo "Docker version 0.0.0-stub"; exit 0 ;;\n'
        f"  info) exit {0 if daemon else 1} ;;\n"
        "  compose)\n"
        '    case "$2" in\n'
        '      version) echo "Docker Compose version v2.0.0-stub"; exit 0 ;;\n'
        "      *) exit 0 ;;\n"
        "    esac ;;\n"
        f"  build) sleep {build_sleep}; exit 0 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
        newline="\n",
    )
    (bin_dir / "docker").chmod(0o755)
    return calls


def _run(cwd: Path, evidence: Path, extra_path: Path | None = None, timeout: int = 120):
    env = dict(os.environ)
    if extra_path is not None:
        env["PATH"] = f"{extra_path}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        [BASH, str(SCRIPT), "--evidence", str(evidence)],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _verdict(evidence: Path) -> dict:
    return json.loads((evidence / "verdict.json").read_text(encoding="utf-8"))


def _pristine_clone(tmp_path: Path) -> Path:
    """A checkout with no modifications, to test the dirtiness report."""
    target = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "--quiet", "--depth", "1", str(ROOT), str(target)],
        check=True,
        capture_output=True,
    )
    return target


# --------------------------------------------------------------------- P1 (1)
def test_an_interrupted_run_never_reports_pass(tmp_path) -> None:
    """A signal must not produce acceptance evidence.

    `pass` used to be the default, changed only by a nonzero failure counter, so
    a run stopped before anything failed reported success it had not earned.
    """
    if sys.platform == "win32":
        pytest.skip("POSIX signal semantics")

    evidence = tmp_path / "evidence"
    calls = _stub_docker(tmp_path, build_sleep=60)

    process = subprocess.Popen(
        [BASH, str(SCRIPT), "--evidence", str(evidence)],
        cwd=str(ROOT),
        env={**os.environ, "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Let it get into the build, then stop it the way a timeout would.
    deadline = time.time() + 60
    while time.time() < deadline:
        if calls.exists() and "build" in calls.read_text(encoding="utf-8"):
            break
        time.sleep(0.5)
    process.send_signal(signal.SIGTERM)
    process.wait(timeout=30)

    verdict = _verdict(evidence)
    assert verdict["verdict"] != "pass", "an interrupted run reported acceptance"
    assert verdict["verdict"] == "incomplete"
    assert verdict["completed"] is False


# --------------------------------------------------------------------- P1 (2)
def test_a_preflight_failure_does_not_tear_down_a_composition_it_never_started(
    tmp_path,
) -> None:
    """The destructive case.

    Port 8000 busy is exactly the situation the preflight exists to catch — and
    it is usually busy because an *earlier* verification run is still up. An
    unconditional `docker compose down -v` would stop that deployment and delete
    its progress volume.
    """
    evidence = tmp_path / "evidence"
    calls = _stub_docker(tmp_path)

    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        holder.bind(("127.0.0.1", 8000))
        holder.listen(1)
    except OSError:
        holder.close()
        pytest.skip("port 8000 is not bindable in this environment")

    try:
        result = _run(ROOT, evidence, extra_path=tmp_path / "bin")
    finally:
        holder.close()

    assert result.returncode == 2, "a busy port is an environment failure"

    invocations = calls.read_text(encoding="utf-8") if calls.exists() else ""
    assert "compose down" not in invocations, (
        "the run tore down a composition it never started; an earlier run's "
        "progress volume would have been destroyed"
    )
    assert "compose up" not in invocations, "nothing should have been started either"
    assert _verdict(evidence)["verdict"] == "environment-failure"


# --------------------------------------------------------------------- P2 (3)
def test_a_pristine_checkout_is_not_reported_as_dirty(tmp_path) -> None:
    """The verifier must not contaminate the condition it records.

    Creating `verification-evidence/verification.log` inside the repository made
    `git status --porcelain` non-empty, so every clean checkout reported dirty.
    """
    clone = _pristine_clone(tmp_path)
    evidence = clone / "verification-evidence"
    # `docker info` failing stops the run at the prerequisite check, right after
    # the environment record this test is about — no build, no health wait.
    _stub_docker(tmp_path, daemon=False)

    _run(clone, evidence, extra_path=tmp_path / "bin")

    recorded = (evidence / "environment.txt").read_text(encoding="utf-8")
    assert "repository_dirty=no" in recorded, (
        f"a freshly cloned checkout was reported as dirty:\n{recorded}"
    )


def test_a_genuinely_dirty_checkout_is_still_reported_as_dirty(tmp_path) -> None:
    """The fix must not simply stop looking."""
    clone = _pristine_clone(tmp_path)
    (clone / "README.md").write_text("modified by the test\n", encoding="utf-8")
    evidence = clone / "verification-evidence"
    _stub_docker(tmp_path, daemon=False)

    _run(clone, evidence, extra_path=tmp_path / "bin")

    recorded = (evidence / "environment.txt").read_text(encoding="utf-8")
    assert "repository_dirty=yes" in recorded


# --------------------------------------------------------------------- P2 (4)
def test_a_bare_evidence_flag_is_a_usage_error(tmp_path) -> None:
    """Malformed invocation must exit 3 deterministically, not spin."""
    result = subprocess.run(
        [BASH, str(SCRIPT), "--evidence"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 3, f"expected usage error, got {result.returncode}"
    assert "requires a directory" in result.stderr


def test_an_empty_evidence_value_is_a_usage_error() -> None:
    result = subprocess.run(
        [BASH, str(SCRIPT), "--evidence", ""],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 3


def test_an_unknown_argument_is_a_usage_error() -> None:
    result = subprocess.run(
        [BASH, str(SCRIPT), "--wat"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 3
