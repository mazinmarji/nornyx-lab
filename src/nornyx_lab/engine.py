"""Lab discovery, the context object each lab is handed, and progress tracking.

A lab is a directory under `labs/` containing:

    lab.toml     metadata: title, chapters covered, objectives, concepts
    README.md    the written lesson (also rendered by `nornyx-lab read`)
    lab.py       `def run(ctx: LabContext) -> None` — the runnable part
    checks.py    pytest tests that verify the learner's understanding
    contract/    a real .nyx contract, when the lab has one

`lab.py` never prints directly. It calls methods on the context, so every lab
gets the same visual language and the engine can capture results for `check`.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import ui
from .constants import LAB_AS_OF, PROGRESS_DIR
from .ledger import Ledger
from .model import Planner, get_planner

try:  # 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.10
    import tomli as tomllib  # type: ignore


def _discover_repo_root() -> Path:
    """The repository root, found by walking up for the `labs/` directory."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "labs").is_dir() and (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


_DISCOVERED_REPO_ROOT = _discover_repo_root()
_REPO_ROOT_OVERRIDE: ContextVar[Path | None] = ContextVar(
    "nornyx_lab_repo_root_override", default=None
)


def repo_root() -> Path:
    """Return the active repository root.

    The ordinary CLI always receives the discovered source root.  Structured
    academy execution may install a context-local override while a copied lab is
    running, so legacy helpers such as ``shared_contract()`` resolve to the same
    isolated workspace without changing process-wide state.
    """

    return _REPO_ROOT_OVERRIDE.get() or _DISCOVERED_REPO_ROOT


def labs_dir() -> Path:
    """Resolve ``labs/`` dynamically against the active repository root."""

    return repo_root() / "labs"


@contextmanager
def using_repo_root(root: Path | str):
    """Temporarily override repository-relative resources in this context."""

    selected = Path(root).resolve()
    token = _REPO_ROOT_OVERRIDE.set(selected)
    try:
        yield selected
    finally:
        _REPO_ROOT_OVERRIDE.reset(token)


# Kept for compatibility with developer code that imported the old constant.
# Runtime discovery uses ``labs_dir()`` so an academy isolation context does not
# accidentally fall back to this process-wide source path.
LABS_DIR = _DISCOVERED_REPO_ROOT / "labs"


# --------------------------------------------------------------------- model
@dataclass(frozen=True)
class LabMeta:
    id: str
    slug: str
    title: str
    part: str
    chapters: str
    difficulty: str
    minutes: int
    objectives: tuple[str, ...]
    concepts: tuple[str, ...]
    requires: tuple[str, ...]
    path: Path

    @property
    def name(self) -> str:
        return f"{self.id} · {self.title}"


def _load_meta(path: Path) -> LabMeta | None:
    toml_path = path / "lab.toml"
    if not toml_path.is_file():
        return None
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    lab = data.get("lab", {})
    return LabMeta(
        id=str(lab.get("id", path.name.split("_")[0])),
        slug=path.name,
        title=str(lab.get("title", path.name)),
        part=str(lab.get("part", "")),
        chapters=str(lab.get("chapters", "")),
        difficulty=str(lab.get("difficulty", "beginner")),
        minutes=int(lab.get("minutes", 15)),
        objectives=tuple(lab.get("objectives", [])),
        concepts=tuple(lab.get("concepts", [])),
        requires=tuple(lab.get("requires", [])),
        path=path,
    )


def all_labs() -> list[LabMeta]:
    root = labs_dir()
    if not root.is_dir():
        return []
    found = [
        meta
        for child in sorted(root.iterdir())
        if child.is_dir() and (meta := _load_meta(child)) is not None
    ]
    return sorted(found, key=lambda m: m.id)


def find_lab(token: str) -> LabMeta | None:
    """Resolve '3', '03', or a slug fragment to a lab."""
    labs = all_labs()
    token = token.strip().lower()
    padded = token.zfill(2) if token.isdigit() else token
    for meta in labs:
        if meta.id == padded or meta.slug == token:
            return meta
    matches = [m for m in labs if token in m.slug.lower() or token in m.title.lower()]
    return matches[0] if len(matches) == 1 else None


# ------------------------------------------------------------------- context
@dataclass
class LabContext:
    """What a lab is given. The methods are the lab authoring vocabulary."""

    meta: LabMeta
    live: bool = False
    as_of: str = LAB_AS_OF
    results: dict[str, Any] = field(default_factory=dict)
    _planner: Planner | None = None

    # ---------------------------------------------------------- environment
    @property
    def dir(self) -> Path:
        return self.meta.path

    @property
    def contract_dir(self) -> Path:
        return self.meta.path / "contract"

    @property
    def planner(self) -> Planner:
        if self._planner is None:
            self._planner = get_planner(self.live)
        return self._planner

    def ledger(self, name: str) -> Ledger:
        return Ledger(name)

    def record(self, key: str, value: Any) -> None:
        """Publish a value for `checks.py` and the notebooks to assert on."""
        self.results[key] = value

    # ------------------------------------------------------------ narration
    def section(self, text: str) -> None:
        ui.section(text)

    def say(self, text: str) -> None:
        ui.say(text)

    def code(self, text: str, lang: str = "python", caption: str = "") -> None:
        ui.code(text, lang, caption)

    def concept(self, name: str, text: str) -> None:
        ui.concept(name, text)

    def boundary(self, text: str) -> None:
        ui.boundary(text)

    def tryit(self, text: str) -> None:
        ui.tryit(text)

    def note(self, text: str) -> None:
        ui.note(text)

    def verdict(self, ok: bool, message: str) -> None:
        ui.verdict(ok, message)

    # ------------------------------------------------------------- toolchain
    def cli(self, result, *, expected_fail: bool = False, show_output: bool = True) -> Any:
        """Render a CliResult, including its diagnostics when it failed."""
        ui.command(
            result.command,
            result.returncode,
            result.stdout if show_output else "",
            expected_fail=expected_fail,
        )
        if not result.ok:
            ui.diagnostics(result.diagnostics())
        return result

    def decisions(self, rows: list[tuple[str, str, str]], caption: str = "") -> None:
        ui.decisions(rows, caption)

    def compare(self, left: Ledger, right: Ledger, actions: list[str] | None = None) -> None:
        ui.ledgers(left, right, actions)


# -------------------------------------------------------------------- runner
def _import_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_lab(meta: LabMeta, *, live: bool = False) -> LabContext:
    """Execute one lab's `run(ctx)` and return the context it filled in."""
    ctx = LabContext(meta=meta, live=live)
    ui.title(meta.id, meta.title, meta.chapters)

    lab_py = meta.path / "lab.py"
    if not lab_py.is_file():
        ui.verdict(False, f"{meta.slug} has no lab.py")
        return ctx

    module = _import_module(lab_py, f"nornyx_lab_labs.{meta.slug}")
    run: Callable[[LabContext], None] | None = getattr(module, "run", None)
    if run is None:
        ui.verdict(False, f"{meta.slug}/lab.py defines no run(ctx)")
        return ctx
    run(ctx)
    return ctx


# ------------------------------------------------------------------ progress
def progress_path() -> Path:
    return repo_root() / PROGRESS_DIR / "progress.json"


def load_progress() -> dict[str, Any]:
    path = progress_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_progress(data: dict[str, Any]) -> None:
    path = progress_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def mark(lab_id: str, status: str) -> None:
    data = load_progress()
    data[lab_id] = status
    save_progress(data)
