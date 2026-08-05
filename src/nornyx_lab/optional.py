"""Optional framework extras, skipped loudly rather than silently.

Labs 13 and 18–20 need CrewAI or LangGraph. The core path must stay installable
without them, so those labs skip — but a *silent* skip is exactly the failure
Chapter 15 warns about: a suite that reports green while asserting nothing.

So skips here are explicit, named, and counted. `nornyx-lab verify` and CI both
run with `-rs`, which prints every skip with its reason, and CI installs the
extras so nothing is skipped there at all.
"""

from __future__ import annotations

from types import ModuleType


class FrameworkMissing(RuntimeError):
    """Raised when an optional framework is absent, with the install command."""

    def __init__(self, framework: str, extra: str) -> None:
        super().__init__(
            f"{framework} is not installed. Install it with:\n"
            f"    uv pip install -e '.[{extra}]'\n"
            f"Every other lab runs without it."
        )
        self.framework = framework
        self.extra = extra


def try_import(module_name: str, *, extra: str) -> ModuleType | None:
    """Import an optional module, or return None if its extra is not installed.

    Catches the adapter's own `MissingOptionalDependencyError` as well as plain
    `ImportError` — the former is not an `ImportError` subclass, so
    `pytest.importorskip` alone does not handle it.
    """
    import importlib

    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None
    except Exception as exc:  # noqa: BLE001
        if type(exc).__name__ == "MissingOptionalDependencyError":
            return None
        raise


def require(module_name: str, *, framework: str, extra: str) -> ModuleType:
    """Import an optional module or raise a FrameworkMissing with instructions."""
    module = try_import(module_name, extra=extra)
    if module is None:
        raise FrameworkMissing(framework, extra)
    return module


def skip_unless(module_name: str, *, extra: str) -> ModuleType:
    """pytest helper: return the module, or skip this test with a clear reason."""
    import pytest

    module = try_import(module_name, extra=extra)
    if module is None:
        pytest.skip(f"{extra} extra not installed — uv pip install -e '.[{extra}]'")
    return module
