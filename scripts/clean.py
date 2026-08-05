"""Remove everything the labs write while running, keeping committed artifacts.

Safe to run at any time. It never touches `contracts/*/control_artifacts`,
`contracts/*/*.lock`, or `contracts/*/governance_evidence` — those are committed
outputs that `scripts/build_contracts.py` owns.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Directories a lab creates as scratch.
SCRATCH_DIRS = [
    "work",
    "generated",
    ".generated-again",
    "fresh",
    "scan-out",
    "audit-package",
    "artifacts-now",
    "drift-probe",
]
SCRATCH_FILES = ["conformance.json", "claim_register.json"]

# Probe contracts a lab writes beside a real one. Each is removed in a `finally`
# during a normal run; an interrupted run can leave one behind, and a stray .nyx
# in contracts/ would then be picked up by the build script.
PROBE_NAMES = [
    "weakened.nyx",
    "weakened_probe.nyx",
    "narrowed_probe.nyx",
    "threat_probe.nyx",
    "gate_probe.nyx",
    "closed_schema_probe.nyx",
    "probe_unknown.nyx",
    "widen_probe.nyx",
]


def main() -> int:
    removed = 0

    for lab in sorted((ROOT / "labs").glob("*/")):
        for name in SCRATCH_DIRS:
            target = lab / name
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
                removed += 1
        for name in SCRATCH_FILES:
            target = lab / name
            if target.is_file():
                target.unlink()
                removed += 1

    for contract in sorted((ROOT / "contracts").glob("*/")):
        for name in PROBE_NAMES:
            target = contract / name
            if target.is_file():
                target.unlink()
                removed += 1
        scratch = contract / ".determinism-probe"
        if scratch.is_dir():
            shutil.rmtree(scratch, ignore_errors=True)
            removed += 1

    for name in (".build-verify", "dist", ".pytest_cache", ".ruff_cache"):
        target = ROOT / name
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            removed += 1

    for cache in ROOT.rglob("__pycache__"):
        if ".venv" not in cache.parts:
            shutil.rmtree(cache, ignore_errors=True)
            removed += 1

    print(f"Removed {removed} scratch item(s). Committed artifacts untouched.")
    print("Your progress is kept — use `nornyx-lab reset` to clear that.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
