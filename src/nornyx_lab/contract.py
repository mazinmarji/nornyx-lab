"""Helpers for driving the real Nornyx toolchain from a lab.

Nothing here reimplements Nornyx. Every function shells out to the installed
`nornyx` CLI or calls the published `nornyx.agentic` SPI, so what a lab shows you
is what the tool actually did — not a lab-flavoured imitation of it.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .constants import LAB_AS_OF


@dataclass(frozen=True)
class CliResult:
    """The outcome of one `nornyx ...` invocation."""

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def command(self) -> str:
        return "nornyx " + " ".join(self.args)

    def diagnostics(self) -> list[dict]:
        """Every diagnostic the command emitted, however it chose to shape it.

        Nornyx prints diagnostics two different ways: `check` emits one
        pretty-printed JSON object per diagnostic (not an array), while
        report-producing commands like `lock-check` emit a single object with a
        nested `diagnostics` list. This walks the output with a raw decoder and
        collects both.
        """
        out: list[dict] = []

        def harvest(value: object) -> None:
            if isinstance(value, dict):
                if "code" in value and "message" in value:
                    out.append(value)
                for nested in value.values():
                    harvest(nested)
            elif isinstance(value, list):
                for item in value:
                    harvest(item)

        blob = (self.stdout + "\n" + self.stderr).strip()
        decoder = json.JSONDecoder()
        index = 0
        while index < len(blob):
            match = re.search(r"[{\[]", blob[index:])
            if not match:
                break
            start = index + match.start()
            try:
                value, end = decoder.raw_decode(blob, start)
            except json.JSONDecodeError:
                index = start + 1
                continue
            harvest(value)
            index = end
        return out

    def codes(self) -> list[str]:
        return [str(d.get("code")) for d in self.diagnostics()]

    def json(self) -> dict | None:
        """The command's structured report, when it produced one."""
        blob = self.stdout.strip()
        if not blob:
            return None
        try:
            value = json.loads(blob)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None


def run_python(args: list[str], cwd: Path | str | None = None) -> subprocess.CompletedProcess:
    """Run a Python module and decode its output as UTF-8 on every platform.

    `text=True` alone decodes with the locale encoding, which on Windows is
    cp1252 and raises `UnicodeDecodeError` the moment a tool prints a box-drawing
    character. Every subprocess in this repository goes through here so the labs
    behave identically on Windows, macOS, and Linux.
    """
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def nornyx(*args: str, cwd: Path | str | None = None) -> CliResult:
    """Run the installed Nornyx CLI and capture everything it said."""
    proc = run_python(["-m", "nornyx.cli", *args], cwd=cwd)
    return CliResult(tuple(args), proc.returncode, proc.stdout, proc.stderr)


# --------------------------------------------------------------- newlines
def normalize_newlines(path: Path | str) -> bool:
    """Rewrite a file with LF line endings. Returns True if it changed.

    WHY THIS EXISTS, and why it is not cheating.

    Python's text writes translate ``\\n`` to ``os.linesep``, so the same
    generator produces CRLF on Windows and LF on Linux. The *content* is
    identical; only the line terminator differs.

    That is fatal for a byte-comparison drift gate: artifacts generated on
    Windows and committed would report drift against a fresh generation on
    Linux CI, on a repository where nothing is wrong.

    So the build pipeline normalizes to LF as an explicit, declared step
    **before** the lock is computed. The digests then bind the normalized
    bytes, and byte-equality means what it says on every platform. This is what
    real pipelines do; the alternative — comparing "bytes, but ignore some of
    them" — would quietly weaken the gate Lab 17 teaches.
    """
    target = Path(path)
    original = target.read_bytes()
    normalized = original.replace(b"\r\n", b"\n")
    if normalized == original:
        return False
    target.write_bytes(normalized)
    return True


def normalize_tree(root: Path | str, patterns: tuple[str, ...] = ("*",)) -> int:
    """Normalize every matching file under `root`. Returns the number changed."""
    base = Path(root)
    changed = 0
    for pattern in patterns:
        for path in sorted(base.rglob(pattern)):
            if path.is_file():
                changed += normalize_newlines(path)
    return changed


def write_text_lf(path: Path | str, text: str) -> Path:
    """Write text with LF endings on every platform."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))
    return target


# ------------------------------------------------------------------- hashing
def content_hash(path: Path | str) -> str:
    """The exact binding Nornyx uses: sha256 over the artifact's bytes."""
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seal_evidence(contract_path: Path | str) -> list[tuple[str, str, str]]:
    """Recompute every `content_hash:` in a contract from the file it names.

    A governance-evidence record binds an id to a *specific* artifact by digest.
    Edit the artifact and the contract stops validating — which is exactly what
    you want, and exactly what makes hand-editing these files tedious.

    Returns one `(artifact, old, new)` triple per record that changed. Lab 12
    tampers with an artifact and uses this to see the binding break and heal.
    """
    path = Path(contract_path)
    root = path.parent
    text = path.read_text(encoding="utf-8")
    changes: list[tuple[str, str, str]] = []

    # Records are emitted as `artifact: <relpath>` followed by `content_hash: ...`
    # within a few lines. Rewrite the digest that follows each artifact line.
    lines = text.splitlines(keepends=True)
    current_artifact: str | None = None
    for index, line in enumerate(lines):
        artifact_match = re.match(r"^\s*artifact:\s*(\S+)\s*$", line)
        if artifact_match:
            current_artifact = artifact_match.group(1)
            continue
        hash_match = re.match(r"^(\s*content_hash:\s*)(\S+)\s*$", line)
        if hash_match and current_artifact:
            target = root / current_artifact
            if target.exists():
                fresh = content_hash(target)
                if fresh != hash_match.group(2):
                    changes.append((current_artifact, hash_match.group(2), fresh))
                    lines[index] = f"{hash_match.group(1)}{fresh}\n"
            current_artifact = None

    if changes:
        write_text_lf(path, "".join(lines))
    return changes


# --------------------------------------------------------------- build chain
def check(contract: Path | str, *, as_of: str = LAB_AS_OF, cwd: Path | None = None) -> CliResult:
    return nornyx("check", str(contract), "--as-of", as_of, cwd=cwd)


def generate(
    contract: Path | str, out: Path | str, *, as_of: str = LAB_AS_OF, cwd: Path | None = None
) -> CliResult:
    return nornyx(
        "agentic-network",
        "generate",
        str(contract),
        "--out",
        str(out),
        "--as-of",
        as_of,
        cwd=cwd,
    )


def lock(
    contract: Path | str,
    artifacts: Path | str,
    out: Path | str,
    *,
    as_of: str = LAB_AS_OF,
    cwd: Path | None = None,
) -> CliResult:
    return nornyx(
        "agentic-network",
        "lock",
        str(contract),
        "--artifacts",
        str(artifacts),
        "--out",
        str(out),
        "--as-of",
        as_of,
        cwd=cwd,
    )


def lock_check(
    contract: Path | str,
    lock_path: Path | str,
    artifacts: Path | str,
    *,
    as_of: str = LAB_AS_OF,
    cwd: Path | None = None,
) -> CliResult:
    return nornyx(
        "agentic-network",
        "lock-check",
        str(contract),
        "--lock",
        str(lock_path),
        "--artifacts",
        str(artifacts),
        "--as-of",
        as_of,
        cwd=cwd,
    )


def build(contract_dir: Path | str, name: str = "network.nyx", *, as_of: str = LAB_AS_OF):
    """Run the whole design-time chain for a lab contract: check, generate, lock.

    Yields `(stage, CliResult)` so a caller can render each step and stop at the
    first failure — the same fail-closed ordering a CI gate uses.
    """
    root = Path(contract_dir)
    contract = root / name
    artifacts = root / "control_artifacts"
    lock_path = root / "nornyx.agentic_network.lock"

    yield "check", check(contract, as_of=as_of)
    yield "generate", generate(contract, artifacts, as_of=as_of)
    yield "lock", lock(contract, artifacts, lock_path, as_of=as_of)
    yield "lock-check", lock_check(contract, lock_path, artifacts, as_of=as_of)


def shared_contract(name: str = "atlas") -> Path:
    """Path to one of the repository's pre-built contracts under `contracts/`.

    These are committed already checked, generated, and locked, so a lab can load
    an authorizer without every learner having to rebuild them first.
    """
    from .engine import repo_root

    return repo_root() / "contracts" / name


def authorizer_for(contract_dir: Path | str, name: str = "network.nyx", *, as_of: str = LAB_AS_OF):
    """Load a lock-verified Authorizer from a lab's contract directory.

    This is the assured construction path from Chapter 19: the contract is
    parsed, checked, composed, governance-evaluated, and verified against its
    lock before any decision is possible. A plain constructor would carry none
    of that, which is precisely why the SPI does not offer you one.
    """
    from nornyx.agentic import load_authorizer

    root = Path(contract_dir)
    return load_authorizer(
        root / name,
        root / "nornyx.agentic_network.lock",
        validation_as_of=as_of,
    )
