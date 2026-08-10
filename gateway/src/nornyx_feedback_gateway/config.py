"""Deployment configuration for the hosted feedback intake.

Everything here is injected at runtime. Nothing in this module carries a default
that would let an unconfigured deployment reach GitHub, and the token is never
placed in a response model, a log record, or an exception message.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

SCHEMA_ID = "nornyx.academy.learner_feedback.v1"

#: ``owner/name``. Deliberately strict: this string is interpolated into a
#: GitHub API path, so anything outside the character set GitHub itself allows
#: is a configuration error rather than something to normalise.
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")

Visibility = Literal["public", "private", "unknown"]


class ConfigurationError(RuntimeError):
    """Raised at startup for an unusable configuration, before any request."""


@dataclass(frozen=True)
class GatewayConfig:
    """One immutable snapshot of the deployment's settings.

    ``github_token`` is the only secret. It is excluded from ``repr`` so an
    accidental log of the config object cannot print it, and no response model
    in this service has a field it could be assigned to.
    """

    github_repository: str | None = None
    github_token: str | None = field(default=None, repr=False)
    github_api: str = "https://api.github.com"
    github_timeout_seconds: float = 10.0
    database_path: str = "gateway.db"
    destination_visibility: Visibility = "unknown"
    issue_labels: tuple[str, ...] = ("learner-feedback",)
    max_body_bytes: int = 64 * 1024
    rate_limit_per_minute: int = 30
    #: How many pages of labelled issues recovery will scan before giving up.
    recovery_page_limit: int = 5

    @property
    def github_configured(self) -> bool:
        return bool(self.github_repository and self.github_token)

    def __post_init__(self) -> None:
        if self.github_repository and not REPOSITORY_PATTERN.match(self.github_repository):
            raise ConfigurationError(
                "NORNYX_FEEDBACK_GITHUB_REPOSITORY must look like 'owner/name'"
            )
        if self.destination_visibility not in ("public", "private", "unknown"):
            raise ConfigurationError(
                "NORNYX_FEEDBACK_DESTINATION_VISIBILITY must be public, private, or unknown"
            )
        if not self.issue_labels:
            raise ConfigurationError("at least one issue label is required")
        for label in self.issue_labels:
            # Labels are attached by this service, never by a learner. Keeping
            # them boring also keeps the "learner text cannot control labels"
            # invariant checkable by inspection.
            if not re.match(r"^[A-Za-z0-9][A-Za-z0-9 ._:-]{0,48}$", label):
                raise ConfigurationError(f"unusable issue label {label!r}")


def _int(source: Mapping[str, str], name: str, fallback: int) -> int:
    raw = source.get(name)
    if raw is None or not raw.strip():
        return fallback
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc


def _float(source: Mapping[str, str], name: str, fallback: float) -> float:
    raw = source.get(name)
    if raw is None or not raw.strip():
        return fallback
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc


def load_config(environ: Mapping[str, str] | None = None) -> GatewayConfig:
    """Read the deployment configuration from a mapping, defaulting to the process environment."""

    source: Mapping[str, str] = os.environ if environ is None else environ
    labels = tuple(
        item.strip()
        for item in source.get("NORNYX_FEEDBACK_ISSUE_LABELS", "learner-feedback").split(",")
        if item.strip()
    )
    visibility = source.get("NORNYX_FEEDBACK_DESTINATION_VISIBILITY") or "unknown"
    return GatewayConfig(
        github_repository=(source.get("NORNYX_FEEDBACK_GITHUB_REPOSITORY") or None),
        github_token=(source.get("NORNYX_FEEDBACK_GITHUB_TOKEN") or None),
        github_api=(source.get("NORNYX_FEEDBACK_GITHUB_API") or "https://api.github.com"),
        github_timeout_seconds=_float(source, "NORNYX_FEEDBACK_GITHUB_TIMEOUT_SECONDS", 10.0),
        database_path=(source.get("NORNYX_FEEDBACK_DB") or "gateway.db"),
        destination_visibility=visibility,  # type: ignore[arg-type]
        issue_labels=labels or ("learner-feedback",),
        max_body_bytes=_int(source, "NORNYX_FEEDBACK_MAX_BODY_BYTES", 64 * 1024),
        rate_limit_per_minute=_int(source, "NORNYX_FEEDBACK_RATE_LIMIT_PER_MINUTE", 30),
    )


__all__ = [
    "SCHEMA_ID",
    "ConfigurationError",
    "GatewayConfig",
    "Visibility",
    "load_config",
]
