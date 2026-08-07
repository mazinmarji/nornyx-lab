"""Structured execution adapter for the 25 legacy ``lab.py`` modules.

The academy imports and calls a lab's ``run(ctx)`` function directly; it never
spawns ``nornyx-lab`` or scrapes Rich/ANSI output.  Every run receives a fresh
copy of mutable training resources, and the engine's context-local repository
override makes legacy ``shared_contract()`` calls resolve inside that copy.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import shutil
import sys
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from pathlib import Path
from textwrap import dedent
from typing import Any
from unittest.mock import patch

from nornyx_lab import ui
from nornyx_lab.engine import LabContext, LabMeta, find_lab, repo_root, using_repo_root
from nornyx_lab.ledger import Ledger
from nornyx_lab.optional import try_import

from .schemas import (
    BlockKind,
    ContentBlock,
    EvidenceFinding,
    EvidenceStatus,
    RunStatus,
    StructuredLabRun,
)

_STRUCTURED_RUN_LOCK = threading.RLock()
_COPIED_DIRECTORIES = ("labs", "contracts", ".github", "scripts")
_COPIED_FILES = ("pyproject.toml", "README.md")
_SENSITIVE_KEY = re.compile(r"(?:api[_-]?key|password|secret|token|credential)", re.IGNORECASE)
_SECRET_VALUE = re.compile(r"(?i)\b(?:sk|api)[-_][A-Za-z0-9_-]{12,}\b")


@dataclass
class StructuredLabContext(LabContext):
    """A ``LabContext`` that emits schema-validated blocks instead of Rich UI."""

    module_id: str = ""
    workspace_root: Path | None = None
    source_root: Path | None = None
    blocks: list[ContentBlock] = field(default_factory=list)
    structured_diagnostics: list[EvidenceFinding] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    verdicts: list[bool] = field(default_factory=list)
    _block_counter: int = 0

    def _text(self, value: str) -> str:
        text = dedent(str(value)).strip()
        for path, marker in (
            (self.workspace_root, "<isolated-workspace>"),
            (self.source_root, "<repository>"),
        ):
            if path is not None:
                text = text.replace(str(path), marker).replace(str(path).replace("\\", "/"), marker)
        return _SECRET_VALUE.sub("<redacted>", text)

    def _add(
        self,
        kind: BlockKind,
        *,
        title: str | None = None,
        body: str = "",
        language: str | None = None,
        rows: tuple[dict[str, Any], ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> ContentBlock:
        self._block_counter += 1
        kind_value = kind.value
        clean_rows = rows
        clean_metadata = metadata or {}
        if self.workspace_root is not None and self.source_root is not None:
            sanitized_rows = _sanitize(
                rows,
                workspace_root=self.workspace_root,
                source_root=self.source_root,
            )
            sanitized_metadata = _sanitize(
                clean_metadata,
                workspace_root=self.workspace_root,
                source_root=self.source_root,
            )
            clean_rows = tuple(
                item for item in sanitized_rows if isinstance(item, dict)
            )
            clean_metadata = (
                sanitized_metadata if isinstance(sanitized_metadata, dict) else {}
            )
        block = ContentBlock(
            id=f"{self.module_id}-{self._block_counter:04d}-{kind_value}",
            kind=kind,
            title=self._text(title) if title else None,
            body=self._text(body),
            language=language,
            rows=clean_rows,
            metadata=clean_metadata,
        )
        self.blocks.append(block)
        return block

    # ------------------------------------------------------------ narration
    def section(self, text: str) -> None:
        self._add(BlockKind.SECTION, title=text)

    def say(self, text: str) -> None:
        self._add(BlockKind.PROSE, body=text, language="markdown")

    def code(self, text: str, lang: str = "python", caption: str = "") -> None:
        self._add(
            BlockKind.CODE,
            title=caption or None,
            body=text,
            language=lang,
        )

    def concept(self, name: str, text: str) -> None:
        self._add(BlockKind.CONCEPT, title=name, body=text, language="markdown")

    def boundary(self, text: str) -> None:
        lowered = str(text).lower()
        if "not installed" in lowered and ("pip install" in lowered or "```bash" in lowered):
            self._add(
                BlockKind.BOUNDARY,
                title="Optional framework unavailable",
                body=(
                    "This lab's real framework section cannot execute in the current server "
                    "environment. The academy reports it as unavailable rather than as success."
                ),
                metadata={
                    "legacy_install_instruction_omitted": True,
                    "terminal_instruction_exposed": False,
                },
            )
            return
        self._add(
            BlockKind.BOUNDARY,
            title="Where this stops",
            body=text,
            language="markdown",
        )

    def tryit(self, text: str) -> None:
        # The original text almost always instructs the learner to edit a file
        # or run a terminal command.  Keep only a flagged placeholder so a
        # learner-facing renderer can hide it and offer a browser-native
        # challenge instead; never leak the manual instruction into the block.
        self._add(
            BlockKind.NOTE,
            title="Legacy manual exercise replaced",
            body=(
                "This legacy exercise requires terminal or manual-file work and is omitted from "
                "the learner view. Use the academy's guided controls for the equivalent challenge."
            ),
            metadata={
                "hidden_from_learner": True,
                "legacy_tryit_omitted": True,
                "original_instruction_present": bool(str(text).strip()),
            },
        )

    def note(self, text: str) -> None:
        self._add(BlockKind.NOTE, body=text, language="markdown")

    def verdict(self, ok: bool, message: str) -> None:
        passed = bool(ok)
        self.verdicts.append(passed)
        check = f"verdict-{len(self.verdicts)}:{'pass' if passed else 'fail'}"
        self.checks.append(check)
        self._add(
            BlockKind.VERDICT,
            title="Executable result",
            body=message,
            metadata={"ok": passed, "check": check},
        )

    # ------------------------------------------------------------- toolchain
    def decisions(self, rows: list[tuple[str, str, str]], caption: str = "") -> None:
        self._add(
            BlockKind.DECISION_TABLE,
            title=caption or "Decision table",
            rows=tuple(
                {"case": str(case), "effect": str(effect), "code": str(code)}
                for case, effect, code in rows
            ),
        )

    def compare(self, left: Ledger, right: Ledger, actions: list[str] | None = None) -> None:
        watched = sorted(actions or (left.touched() | right.touched()))
        self._add(
            BlockKind.LEDGER_COMPARISON,
            title="What each run actually caused",
            rows=tuple(
                {
                    "action": action,
                    "left_attempts": left.attempts(action),
                    "left_completions": left.completions(action),
                    "right_attempts": right.attempts(action),
                    "right_completions": right.completions(action),
                    "changed": (left.attempts(action), left.completions(action))
                    != (right.attempts(action), right.completions(action)),
                }
                for action in watched
            ),
            metadata={"left": left.name, "right": right.name},
        )

    def cli(self, result: Any, *, expected_fail: bool = False, show_output: bool = True) -> Any:
        """Capture a legacy tool result without exposing terminal transcript text."""

        try:
            raw_diagnostics = result.diagnostics()
        except Exception:  # a foreign legacy result still gets an explicit failure row
            raw_diagnostics = []
        rows = tuple(_diagnostic_row(item) for item in raw_diagnostics if isinstance(item, dict))
        ok = bool(getattr(result, "ok", False))
        if not rows and not ok:
            rows = (
                {
                    "code": "LEGACY_TOOL_FAILED",
                    "path": None,
                    "message": "The legacy Nornyx operation returned a non-zero status.",
                    "level": "error",
                },
            )
        block = self._add(
            BlockKind.DIAGNOSTICS,
            title="Nornyx operation result",
            rows=rows,
            metadata={
                "ok": ok,
                "expected_failure": bool(expected_fail),
                "returncode": int(getattr(result, "returncode", -1)),
                "terminal_transcript_hidden": True,
                "show_output_requested_by_legacy_lab": bool(show_output),
            },
        )
        for row in block.rows:
            self.structured_diagnostics.append(_finding_from_row(row))
        return result

    def capture_diagnostics(self, items: list[dict[str, Any]], *, title: str = "Diagnostics") -> None:
        rows = tuple(_diagnostic_row(item) for item in items if isinstance(item, dict))
        block = self._add(BlockKind.DIAGNOSTICS, title=title, rows=rows)
        self.structured_diagnostics.extend(_finding_from_row(row) for row in block.rows)

    def capture_direct_command(
        self,
        command: str,
        returncode: int,
        output: str = "",
        *,
        expected_fail: bool = False,
    ) -> None:
        # Lab 20 calls ui.command directly.  Preserve only structured status;
        # neither the command nor its terminal output belongs in the GUI model.
        ok = returncode == 0
        rows: tuple[dict[str, Any], ...] = ()
        if not ok:
            rows = (
                {
                    "code": "LEGACY_OPERATION_NONZERO",
                    "path": None,
                    "message": "The direct legacy operation returned a non-zero status.",
                    "level": "warning" if expected_fail else "error",
                },
            )
        block = self._add(
            BlockKind.DIAGNOSTICS,
            title="Legacy operation result",
            rows=rows,
            metadata={
                "ok": ok,
                "expected_failure": expected_fail,
                "returncode": returncode,
                "command_hidden": bool(command),
                "terminal_output_hidden": bool(output),
            },
        )
        self.structured_diagnostics.extend(_finding_from_row(row) for row in block.rows)


def _diagnostic_row(item: dict[str, Any]) -> dict[str, Any]:
    level = str(item.get("level", "warning"))
    return {
        "code": str(item.get("code", "NORNYX_DIAGNOSTIC")),
        "path": str(item["path"]) if item.get("path") is not None else None,
        "message": str(item.get("message", "Nornyx returned a diagnostic.")),
        "level": level,
    }


def _finding_from_row(row: dict[str, Any]) -> EvidenceFinding:
    level = str(row.get("level", "warning"))
    return EvidenceFinding(
        status=(
            EvidenceStatus.FAIL
            if level == "error"
            else EvidenceStatus.UNKNOWN
            if level == "warning"
            else EvidenceStatus.PASS
        ),
        code=str(row.get("code", "NORNYX_DIAGNOSTIC")),
        message=str(row.get("message", "Nornyx returned a diagnostic.")),
        path=str(row["path"]) if row.get("path") is not None else None,
    )


def _copy_workspace(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in _COPIED_DIRECTORIES:
        origin = source / name
        if origin.exists():
            shutil.copytree(origin, target / name)
    for name in _COPIED_FILES:
        origin = source / name
        if origin.is_file():
            shutil.copy2(origin, target / name)


def _load_lab_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import copied lab module {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _sanitize(
    value: Any,
    *,
    workspace_root: Path,
    source_root: Path,
    key: str = "",
    depth: int = 0,
) -> Any:
    if depth > 12:
        return "<maximum-depth>"
    if key and _SENSITIVE_KEY.search(key):
        return "<redacted>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Enum):
        return _sanitize(
            value.value,
            workspace_root=workspace_root,
            source_root=source_root,
            key=key,
            depth=depth + 1,
        )
    if isinstance(value, Path):
        try:
            return f"<isolated-workspace>/{value.resolve().relative_to(workspace_root.resolve()).as_posix()}"
        except (OSError, ValueError):
            try:
                return f"<repository>/{value.resolve().relative_to(source_root.resolve()).as_posix()}"
            except (OSError, ValueError):
                return f"<external-path>/{value.name}"
    if isinstance(value, str):
        text = value
        text = text.replace(str(workspace_root), "<isolated-workspace>")
        text = text.replace(str(source_root), "<repository>")
        text = _SECRET_VALUE.sub("<redacted>", text)
        return text if len(text) <= 20_000 else text[:20_000] + "… <truncated>"
    if is_dataclass(value) and not isinstance(value, type):
        return _sanitize(
            asdict(value),
            workspace_root=workspace_root,
            source_root=source_root,
            key=key,
            depth=depth + 1,
        )
    if isinstance(value, dict):
        return {
            str(item_key): _sanitize(
                item_value,
                workspace_root=workspace_root,
                source_root=source_root,
                key=str(item_key),
                depth=depth + 1,
            )
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [
            _sanitize(
                item,
                workspace_root=workspace_root,
                source_root=source_root,
                depth=depth + 1,
            )
            for item in value
        ]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _sanitize(
                to_dict(),
                workspace_root=workspace_root,
                source_root=source_root,
                key=key,
                depth=depth + 1,
            )
        except Exception:
            pass
    return f"<{type(value).__name__}>"


def _framework_unavailable(lab_id: str) -> str | None:
    if lab_id == "18":
        if try_import("nornyx_agentic_adapters.crewai_adapter", extra="crewai") is None:
            return (
                "CrewAI support is not installed, so the real adapter section is unavailable. "
                "The academy does not treat the omitted execution as success."
            )
    if lab_id == "19":
        adapter = try_import("nornyx_agentic_adapters.langgraph", extra="langgraph")
        framework = try_import("langgraph.graph", extra="langgraph")
        if adapter is None or framework is None:
            return (
                "LangGraph support is not installed, so the real graph execution is unavailable. "
                "The academy does not treat the omitted execution as success."
            )
    if lab_id == "20":
        crewai = try_import("nornyx_agentic_adapters.crewai_adapter", extra="crewai")
        langgraph = try_import("nornyx_agentic_adapters.langgraph", extra="langgraph")
        graph = try_import("langgraph.graph", extra="langgraph")
        if crewai is None or langgraph is None or graph is None:
            return (
                "The adapter-conformance section requires both CrewAI and LangGraph support. "
                "At least one is not installed, so the structured run is explicitly unavailable "
                "instead of treating skipped conformance surfaces as success."
            )
    return None


@contextmanager
def _capture_legacy_ui(ctx: StructuredLabContext):
    """Redirect the few legacy modules that call ``ui`` without their context."""

    with patch.multiple(
        ui,
        title=lambda lab_id, name, chapters="": None,
        section=ctx.section,
        say=ctx.say,
        code=ctx.code,
        concept=ctx.concept,
        boundary=ctx.boundary,
        tryit=ctx.tryit,
        note=ctx.note,
        verdict=ctx.verdict,
        decisions=ctx.decisions,
        ledgers=ctx.compare,
        diagnostics=lambda items, limit=8: ctx.capture_diagnostics(items[:limit]),
        command=ctx.capture_direct_command,
    ):
        yield


def _unavailable_live_run(meta: LabMeta, module_id: str) -> StructuredLabRun:
    reason = (
        "Legacy structured labs do not call a live model. No deterministic fixture is substituted "
        "for a requested live execution."
    )
    return StructuredLabRun(
        run_id=f"structured-{meta.id}-live-unavailable",
        module_id=module_id,
        legacy_lab_id=meta.id,
        title=meta.title,
        status=RunStatus.UNAVAILABLE,
        blocks=(
            ContentBlock(
                id=f"{module_id}-0001-boundary",
                kind=BlockKind.BOUNDARY,
                title="Live execution unavailable",
                body=reason,
            ),
        ),
        results={},
        completion_eligible=False,
        unavailable_reason=reason,
        safety_boundary="No model call, tool call, or external effect was attempted.",
    )


def run_structured_lab(
    token: str,
    *,
    module_id: str | None = None,
    live: bool = False,
) -> StructuredLabRun:
    """Run a legacy lab against a fresh copied workspace and return typed blocks."""

    source = repo_root()
    meta = find_lab(token)
    if meta is None:
        raise KeyError(f"unknown legacy lab: {token}")
    selected_module = module_id or f"lab-{meta.id}"
    if live:
        return _unavailable_live_run(meta, selected_module)

    run_seed = f"{meta.id}:{selected_module}:deterministic"
    run_id = f"structured-{hashlib.sha256(run_seed.encode('utf-8')).hexdigest()[:16]}"
    framework_reason = _framework_unavailable(meta.id)

    # Legacy modules can temporarily patch UI functions and several labs mutate
    # their own fixtures. Serializing this narrow compatibility boundary avoids
    # process-global module/UI races while each run still gets isolated files.
    with _STRUCTURED_RUN_LOCK:
        with tempfile.TemporaryDirectory(prefix=f"nornyx-lab-{meta.id}-") as temporary:
            isolated = Path(temporary) / "workspace"
            _copy_workspace(source, isolated)
            module_name = f"nornyx_lab_structured_{meta.id}_{hashlib.sha256(str(isolated).encode()).hexdigest()[:12]}"

            with using_repo_root(isolated):
                copied_meta = find_lab(meta.id)
                if copied_meta is None:
                    raise RuntimeError(f"isolated copy is missing lab {meta.id}")
                ctx = StructuredLabContext(
                    meta=copied_meta,
                    live=False,
                    module_id=selected_module,
                    workspace_root=isolated,
                    source_root=source,
                )
                status = RunStatus.COMPLETE
                unavailable_reason = framework_reason
                try:
                    with _capture_legacy_ui(ctx):
                        module = _load_lab_module(copied_meta.path / "lab.py", module_name)
                        run = getattr(module, "run", None)
                        if not callable(run):
                            raise RuntimeError("lab.py does not define callable run(ctx)")
                        run(ctx)
                except Exception as exc:
                    status = RunStatus.FAILED
                    failure = EvidenceFinding(
                        status=EvidenceStatus.FAIL,
                        code="LAB_EXECUTION_FAILED",
                        message=ctx._text(
                            f"The isolated legacy lab failed ({type(exc).__name__}): {exc}"
                        ),
                        path=f"labs/{copied_meta.slug}/lab.py",
                    )
                    ctx.structured_diagnostics.append(failure)
                    ctx._add(
                        BlockKind.DIAGNOSTICS,
                        title="Lab execution failed",
                        rows=(
                            {
                                "code": failure.code,
                                "path": failure.path,
                                "message": failure.message,
                                "level": "error",
                            },
                        ),
                    )
                finally:
                    sys.modules.pop(module_name, None)

                if status == RunStatus.COMPLETE and framework_reason is not None:
                    status = RunStatus.UNAVAILABLE
                    ctx.structured_diagnostics.append(
                        EvidenceFinding(
                            status=EvidenceStatus.MISSING,
                            code="OPTIONAL_FRAMEWORK_UNAVAILABLE",
                            message=framework_reason,
                        )
                    )
                    ctx._add(
                        BlockKind.DIAGNOSTICS,
                        title="Framework execution unavailable",
                        rows=(
                            {
                                "code": "OPTIONAL_FRAMEWORK_UNAVAILABLE",
                                "path": None,
                                "message": framework_reason,
                                "level": "warning",
                            },
                        ),
                    )

                sanitized = _sanitize(
                    ctx.results,
                    workspace_root=isolated,
                    source_root=source,
                )
                assert isinstance(sanitized, dict)
                sanitized["_academy"] = {
                    "isolated_workspace": True,
                    "source_workspace_writable_by_lab": False,
                    "terminal_transcripts_exposed": False,
                    "legacy_tryit_blocks": sum(
                        1 for block in ctx.blocks if block.metadata.get("legacy_tryit_omitted")
                    ),
                    "verdicts": list(ctx.verdicts),
                }
                # Execution eligibility is not course completion: the progress
                # service still requires the module's assessment.  It means the
                # full structured lab ran (including its intentional negative
                # controls) without an unavailable dependency or execution
                # failure. A red legacy "verdict" can itself be the expected
                # unsafe outcome demonstrated by the lesson (Lab 00).
                completion_eligible = status == RunStatus.COMPLETE
                return StructuredLabRun(
                    run_id=run_id,
                    module_id=selected_module,
                    legacy_lab_id=copied_meta.id,
                    title=copied_meta.title,
                    status=status,
                    blocks=tuple(ctx.blocks),
                    results=sanitized,
                    diagnostics=tuple(ctx.structured_diagnostics),
                    executable_checks=tuple(ctx.checks),
                    completion_eligible=completion_eligible,
                    unavailable_reason=unavailable_reason,
                    safety_boundary=(
                        "The legacy lab ran against a fresh temporary copy of labs, contracts, and "
                        "generated fixtures. Northstar business tools are inert; the source workspace "
                        "was never supplied as a mutation target."
                    ),
                )


# Compatibility aliases for router/service call sites.
execute_structured_lab = run_structured_lab
run_lab_structured = run_structured_lab


__all__ = [
    "StructuredLabContext",
    "execute_structured_lab",
    "run_lab_structured",
    "run_structured_lab",
]
