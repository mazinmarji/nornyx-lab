"""One place that answers "which versions is this installation actually running?".

Both the platform endpoint and the feedback context need this, and they must
agree: a learner rating recorded against one set of version numbers while the
about page shows another would make the whole corpus unreadable.
"""

from __future__ import annotations

from importlib import metadata


def package_version(distribution: str, fallback: str) -> str:
    """The installed version, or the declared fallback when it is not installed.

    The fallback is what the repository pins, so a source checkout without
    installed metadata reports the version it is pinned to rather than
    ``unknown``.
    """

    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return fallback


def academy_version() -> str:
    return package_version("nornyx-lab", "2.0.0")


def nornyx_version() -> str:
    return package_version("nornyx", "1.11.0")


def adapter_version() -> str:
    return package_version("nornyx-agentic-adapters", "0.3.0")


__all__ = ["academy_version", "adapter_version", "nornyx_version", "package_version"]
