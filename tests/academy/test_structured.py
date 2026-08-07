from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from nornyx_lab import optional
from nornyx_lab.academy import structured
from nornyx_lab.academy.schemas import BlockKind, RunStatus
from nornyx_lab.engine import all_labs, repo_root

ROOT = repo_root()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_legacy_lab_runs_directly_into_structured_schema() -> None:
    result = structured.run_structured_lab("00")

    assert result.status == RunStatus.COMPLETE
    assert result.legacy_lab_id == "00"
    assert result.module_id == "lab-00"
    assert result.results["publish_attempts"] == 1
    assert result.results["publish_completions"] == 1
    assert result.results["_academy"]["isolated_workspace"] is True
    assert result.results["_academy"]["terminal_transcripts_exposed"] is False
    assert {block.kind for block in result.blocks}.issuperset(
        {
            BlockKind.SECTION,
            BlockKind.PROSE,
            BlockKind.CODE,
            BlockKind.CONCEPT,
            BlockKind.BOUNDARY,
            BlockKind.VERDICT,
            BlockKind.LEDGER_COMPARISON,
        }
    )
    assert result.safety_boundary
    # Pydantic serialization is the actual browser/API boundary.
    assert result.model_dump_json().startswith('{"api_version":"v1"')


def test_legacy_manual_tryit_text_is_omitted_and_flagged() -> None:
    result = structured.run_structured_lab("00")
    manual = [block for block in result.blocks if block.metadata.get("legacy_tryit_omitted")]

    assert manual
    assert all(block.metadata["hidden_from_learner"] is True for block in manual)
    assert all("nornyx-lab" not in block.body for block in manual)
    assert all("python " not in block.body.lower() for block in manual)
    assert result.results["_academy"]["legacy_tryit_blocks"] == len(manual)


def test_structured_results_are_deterministic_and_do_not_leak_local_paths() -> None:
    first = structured.run_structured_lab("00")
    second = structured.run_structured_lab("00")

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    serialized = first.model_dump_json()
    assert str(ROOT) not in serialized
    assert "nornyx-lab-00-" not in serialized


def test_missing_framework_is_explicitly_unavailable_not_success(monkeypatch) -> None:
    def missing(module_name: str, *, extra: str):
        return None

    monkeypatch.setattr(structured, "try_import", missing)
    monkeypatch.setattr(optional, "try_import", missing)
    result = structured.run_structured_lab("18")

    assert result.status == RunStatus.UNAVAILABLE
    assert result.completion_eligible is False
    assert result.unavailable_reason is not None
    assert "not installed" in result.unavailable_reason
    assert "OPTIONAL_FRAMEWORK_UNAVAILABLE" in {item.code for item in result.diagnostics}


def test_representative_mutating_lab_cannot_change_source_fixtures() -> None:
    watched = (
        ROOT / "contracts/atlas/network.nyx",
        ROOT / "contracts/atlas/nornyx.agentic_network.lock",
        ROOT / "contracts/atlas/control_artifacts/trust_zone_map.json",
    )
    before = {path: _digest(path) for path in watched}

    result = structured.run_structured_lab("15")

    assert result.status == RunStatus.COMPLETE
    assert result.results["restored_ok"] is True
    assert result.results["lock_failure_modes"] == 3
    assert {path: _digest(path) for path in watched} == before
    assert repo_root() == ROOT
    assert all(meta.path.is_relative_to(ROOT) for meta in all_labs())


def test_live_legacy_lab_request_is_explicitly_unavailable() -> None:
    result = structured.run_structured_lab("00", live=True)
    assert result.status == RunStatus.UNAVAILABLE
    assert result.unavailable_reason
    assert result.blocks[0].kind == BlockKind.BOUNDARY


def _missing_all_labs_extras() -> tuple[str, ...]:
    missing: list[str] = []
    if optional.try_import(
        "nornyx_agentic_adapters.crewai_adapter", extra="crewai"
    ) is None:
        missing.append("crewai")
    if (
        optional.try_import("nornyx_agentic_adapters.langgraph", extra="langgraph") is None
        or optional.try_import("langgraph.graph", extra="langgraph") is None
    ):
        missing.append("langgraph")
    return tuple(missing)


@pytest.mark.all_labs
def test_all_25_legacy_labs_complete_through_structured_migration() -> None:
    """Slow quality gate: every legacy lesson must execute as browser-native data."""

    missing_extras = _missing_all_labs_extras()
    if missing_extras:
        pytest.skip(
            "the all-labs migration gate requires optional extras: "
            + ", ".join(missing_extras)
        )

    watched = (
        ROOT / "pyproject.toml",
        ROOT / "labs/15_profiles_and_locks/lab.py",
        ROOT / "contracts/atlas/network.nyx",
        ROOT / "contracts/atlas/nornyx.agentic_network.lock",
        ROOT / "contracts/atlas/control_artifacts/trust_zone_map.json",
        ROOT / "contracts/ledger/network.nyx",
        ROOT / "contracts/ledger/nornyx.agentic_network.lock",
    )
    before = {path: _digest(path) for path in watched}

    try:
        for index in range(25):
            legacy_id = f"{index:02d}"
            result = structured.run_structured_lab(legacy_id, module_id=legacy_id)

            assert result.status == RunStatus.COMPLETE, (
                legacy_id,
                result.unavailable_reason,
                result.diagnostics,
            )
            assert result.legacy_lab_id == legacy_id
            assert result.module_id == legacy_id
            assert result.completion_eligible is True
            assert result.results["_academy"]["terminal_transcripts_exposed"] is False
            assert all(
                block.metadata.get("terminal_transcript_hidden") is not False
                and block.metadata.get("terminal_output_hidden") is not False
                for block in result.blocks
            )
    finally:
        assert {path: _digest(path) for path in watched} == before
        assert repo_root() == ROOT
