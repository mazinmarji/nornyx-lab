"""Process-local live-model configuration with an explicit secret boundary."""

from __future__ import annotations

import threading
from importlib.util import find_spec

from pydantic import SecretStr

from nornyx_lab.model import LivePlanner

from .schemas import LiveModelSettingsRequest, LiveModelSettingsResponse


class LiveModelSettingsStore:
    """Holds one optional API key in memory and never serializes it.

    The browser academy is deterministic and offline by default. Live mode is
    intentionally process-local: restarting the server clears the key, progress
    exports omit it, and response objects expose only a configured flag.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._enabled = False
        self._provider = "anthropic"
        self._model = LivePlanner.MODEL
        self._api_key: SecretStr | None = None

    def response(self) -> LiveModelSettingsResponse:
        with self._lock:
            return LiveModelSettingsResponse(
                enabled=self._enabled,
                provider=self._provider,
                model=self._model,
                configured=self._api_key is not None,
                persisted=False,
                boundary=(
                    "Live mode is optional and non-deterministic. The API key exists only in "
                    "this server process, is never returned, logged, or written to learner "
                    "progress, and is cleared when live mode is disabled or the server restarts."
                ),
            )

    def configure(self, request: LiveModelSettingsRequest) -> LiveModelSettingsResponse:
        with self._lock:
            self._provider = request.provider
            self._model = request.model.strip()
            if not self._model:
                raise ValueError("model must not be blank")
            if request.enabled:
                if find_spec("anthropic") is None:
                    raise ValueError(
                        "live-model support is not installed in this academy deployment"
                    )
                if request.api_key is not None:
                    value = request.api_key.get_secret_value().strip()
                    if not value:
                        raise ValueError("api_key must not be blank when supplied")
                    self._api_key = SecretStr(value)
                if self._api_key is None:
                    raise ValueError("an API key is required to enable live mode")
                self._enabled = True
            else:
                self._enabled = False
                self._api_key = None
        return self.response()

    def planner(self) -> LivePlanner:
        with self._lock:
            if not self._enabled or self._api_key is None:
                raise RuntimeError("live model mode is not enabled and configured")
            return LivePlanner(
                model=self._model,
                api_key=self._api_key.get_secret_value(),
            )
