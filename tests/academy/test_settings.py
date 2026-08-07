from __future__ import annotations

import pytest

from nornyx_lab.academy.schemas import LiveModelSettingsRequest
from nornyx_lab.academy.settings import LiveModelSettingsStore


def test_live_settings_require_a_key_and_never_return_it() -> None:
    store = LiveModelSettingsStore()

    with pytest.raises(ValueError, match="API key"):
        store.configure(LiveModelSettingsRequest(enabled=True))

    response = store.configure(
        LiveModelSettingsRequest(
            enabled=True,
            model="claude-sonnet-4-20250514",
            api_key="secret-test-value",
        )
    )

    payload = response.model_dump(mode="json")
    assert response.enabled is True
    assert response.configured is True
    assert response.persisted is False
    assert "secret-test-value" not in str(payload)
    assert "api_key" not in payload


def test_disabling_live_mode_clears_process_local_secret() -> None:
    store = LiveModelSettingsStore()
    store.configure(LiveModelSettingsRequest(enabled=True, api_key="secret-test-value"))

    disabled = store.configure(LiveModelSettingsRequest(enabled=False))

    assert disabled.enabled is False
    assert disabled.configured is False
    with pytest.raises(RuntimeError, match="not enabled"):
        store.planner()
