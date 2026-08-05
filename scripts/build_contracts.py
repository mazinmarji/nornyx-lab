"""Author-side build for the repository's contracts.

Writes the governance-evidence artifacts, reseals every `content_hash` against
them, then runs check -> generate -> lock -> lock-check for each contract. The
outputs are committed, so a learner who clones this repo gets a tree where
`nornyx agentic-network lock-check` already passes.

    python scripts/build_contracts.py            # build all
    python scripts/build_contracts.py atlas      # build one

CI runs this with --verify, which rebuilds into a temporary directory and fails
if anything differs from what is committed. That is the drift gate from Lab 17,
applied to the lab itself.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from nornyx_lab.constants import LAB_AS_OF, LAB_SUBJECT_REVISION  # noqa: E402
from nornyx_lab.contract import (  # noqa: E402
    normalize_newlines,
    normalize_tree,
    seal_evidence,
    write_text_lf,
)

CONTRACTS = ROOT / "contracts"

# Every contract needs these three records; the profile requires two of them by
# id and type. Content is deliberately small and human-readable.
EVIDENCE = {
    "evidence_manifest.json": {
        "evidence_type": "evidence_manifest",
        "status": "pass",
        "subject_revision": LAB_SUBJECT_REVISION,
    },
    "independent_review_record.json": {
        "evidence_type": "network_contract_review",
        "reviewer_role": "security_reviewer",
        "status": "pass",
        "subject_revision": LAB_SUBJECT_REVISION,
        "summary": "Static review of the network contract at the pinned revision.",
    },
    "approval_record.json": {
        "actor_type": "human",
        "approver_role": "network_governance_owner",
        "evidence_type": "approval_record",
        "scope": "approve_agentic_network_contract",
        "status": "pass",
        "subject_revision": LAB_SUBJECT_REVISION,
    },
}


def nx(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "nornyx.cli", *args], cwd=str(cwd), capture_output=True, text=True
    )


def build(contract_dir: Path, *, quiet: bool = False) -> bool:
    name = contract_dir.name
    contract = contract_dir / "network.nyx"
    if not contract.is_file():
        print(f"  {name}: no network.nyx, skipping")
        return True

    # 0. the source itself, so an editor that saved CRLF cannot change any
    #    digest computed over these bytes on one platform but not another.
    normalize_newlines(contract)

    # 1. evidence artifacts
    ev_dir = contract_dir / "governance_evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in EVIDENCE.items():
        body = dict(payload)
        if filename == "evidence_manifest.json":
            body["scope"] = f"governed {name} network"
        write_text_lf(ev_dir / filename, json.dumps(body, sort_keys=True, separators=(",", ":")))

    # 2. bind the contract to those exact bytes
    seal_evidence(contract)

    # 3. the design-time chain, fail-closed at the first bad stage
    artifacts = contract_dir / "control_artifacts"
    lock_path = contract_dir / "nornyx.agentic_network.lock"
    stages = [
        ("check", ("check", "network.nyx", "--as-of", LAB_AS_OF)),
        # The profiles lock is a SEPARATE control from the agentic-network lock:
        # it binds which profile and module versions composed this contract.
        # Lab 07 reads it; `governance matrix` reports "absent" without it.
        ("profiles-lock", ("profiles", "resolve", "agentic_network", "--lock")),
        (
            "generate",
            (
                "agentic-network",
                "generate",
                "network.nyx",
                "--out",
                "control_artifacts",
                "--as-of",
                LAB_AS_OF,
            ),
        ),
        (
            "lock",
            (
                "agentic-network",
                "lock",
                "network.nyx",
                "--artifacts",
                "control_artifacts",
                "--out",
                "nornyx.agentic_network.lock",
                "--as-of",
                LAB_AS_OF,
            ),
        ),
        (
            "lock-check",
            (
                "agentic-network",
                "lock-check",
                "network.nyx",
                "--lock",
                "nornyx.agentic_network.lock",
                "--artifacts",
                "control_artifacts",
                "--as-of",
                LAB_AS_OF,
            ),
        ),
    ]
    for stage, args in stages:
        result = nx(*args, cwd=contract_dir)
        if result.returncode != 0:
            print(f"  {name}: {stage} FAILED (exit {result.returncode})")
            print(result.stdout[:3000])
            print(result.stderr[:1500])
            return False

        # Normalize BEFORE the lock is computed, so the digests bind LF bytes
        # and byte-comparison means the same thing on Windows and Linux.
        # See nornyx_lab.contract.normalize_newlines for the full reasoning.
        if stage == "generate":
            normalize_tree(artifacts)
        elif stage == "profiles-lock":
            normalize_newlines(contract_dir / "nornyx.profiles.lock")

        if not quiet:
            print(f"  {name}: {stage} ok")

    assert artifacts.is_dir() and lock_path.is_file()
    return True


def _rmtree(path: Path) -> None:
    """Remove a tree, tolerating a transient Windows file lock.

    An antivirus scan or an indexer can hold a freshly written file for a
    moment. Failing the drift gate because of that would be a false negative on
    exactly the control this repository is teaching, so retry briefly.
    """
    for attempt in range(5):
        try:
            shutil.rmtree(path, ignore_errors=False)
            return
        except (PermissionError, OSError):
            if attempt == 4:
                shutil.rmtree(path, ignore_errors=True)
                return
            time.sleep(0.2 * (attempt + 1))


# Several labs write a deliberately-broken contract beside a real one to show a
# diagnostic, and delete it in a `finally`. An interrupted run can leave one
# behind. Those files are never part of the committed set, so the drift gate
# must not compare them — otherwise an aborted lab makes a correct repository
# look drifted, and the gate gets a reputation for lying.
PROBE_SUFFIXES = ("_probe.nyx", "weakened.nyx", "widen_probe.nyx")


def _is_probe(path: Path) -> bool:
    return path.name.endswith(PROBE_SUFFIXES) or path.name.startswith(".")


def verify() -> bool:
    """Rebuild into a scratch copy and compare against what is committed."""
    scratch = ROOT / ".build-verify"
    if scratch.exists():
        _rmtree(scratch)
    shutil.copytree(
        CONTRACTS,
        scratch,
        ignore=lambda _dir, names: [n for n in names if _is_probe(Path(n))],
    )

    ok = True
    for child in sorted(scratch.iterdir()):
        if child.is_dir():
            ok = build(child, quiet=True) and ok

    if ok:
        for child in sorted(CONTRACTS.iterdir()):
            if not child.is_dir():
                continue
            for path in sorted(child.rglob("*")):
                if path.is_dir() or _is_probe(path):
                    continue
                mirror = scratch / path.relative_to(CONTRACTS)
                if not mirror.is_file() or mirror.read_bytes() != path.read_bytes():
                    print(f"  DRIFT: {path.relative_to(ROOT)}")
                    ok = False

    _rmtree(scratch)
    print("  no drift" if ok else "  drift detected")
    return ok


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--verify" in sys.argv:
        print("Verifying committed contract artifacts…")
        return 0 if verify() else 1

    targets = (
        [CONTRACTS / a for a in args]
        if args
        else [c for c in sorted(CONTRACTS.iterdir()) if c.is_dir()]
    )
    print("Building contracts…")
    ok = True
    for target in targets:
        ok = build(target) and ok
    print("done" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
