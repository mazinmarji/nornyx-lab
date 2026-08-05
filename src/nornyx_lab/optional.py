"""Optional framework extras, skipped loudly rather than silently.

Labs 13 and 18–20 need CrewAI or LangGraph. The core path must stay installable
without them, so those labs skip — but a *silent* skip is exactly the failure
Chapter 15 warns about: a suite that reports green while asserting nothing.

So skips here are explicit, named, and counted. `nornyx-lab verify` and CI both
run with `-rs`, which prints every skip with its reason, and CI installs the
extras so nothing is skipped there at all.
"""

from __future__ import annotations

import os
from types import ModuleType

# ---------------------------------------------------------------------------
# CrewAI first-run kill switches. These MUST be set before the first `crewai`
# import anywhere in the process, so they live at module import time and every
# framework import in this repository goes through the helpers below.
#
# On a *fresh* install CrewAI runs a one-time tracing-consent step that prints a
# banner, writes a preference file, and spawns a process. The adapter's
# conformance suite runs guarded — a conforming suite must not spawn a process —
# so that first run makes conformance report `nonconformant` on a clean machine
# while passing on any machine where CrewAI has already been run once.
#
# That is a genuinely nasty failure mode: it passes locally for the author and
# fails in CI, and the error names process execution rather than telemetry.
# `CREWAI_TESTING` short-circuits the consent step entirely; the other three
# switch off telemetry and tracing. None of them changes the model or the
# `Crew.kickoff()` execution path, so the labs observe the same behaviour.
for _key, _value in (
    ("CREWAI_DISABLE_TELEMETRY", "true"),
    ("OTEL_SDK_DISABLED", "true"),
    ("CREWAI_TRACING_ENABLED", "false"),
    ("CREWAI_TESTING", "true"),
):
    os.environ.setdefault(_key, _value)


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
