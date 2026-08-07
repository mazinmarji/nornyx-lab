"""Fast checks for the six browser-native foundation interactions."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from nornyx_lab.academy.foundations import (
    FOUNDATION_MODULE_IDS,
    FoundationInputError,
    run_foundation,
)
from nornyx_lab.academy.schemas import RunStatus, StructuredLabRun
from nornyx_lab.contract import shared_contract


@pytest.mark.parametrize("module_id", FOUNDATION_MODULE_IDS)
def test_every_foundation_returns_a_complete_structured_browser_run(module_id: str) -> None:
    result = run_foundation(module_id)

    assert isinstance(result, StructuredLabRun)
    assert result.module_id == module_id
    assert result.status == RunStatus.COMPLETE.value
    assert result.blocks
    assert result.executable_checks
    assert result.safety_boundary
    assert "terminal" not in result.results


def test_f0_uses_the_real_ab_scenario_without_mutating_the_contract() -> None:
    files = (
        shared_contract("atlas") / "network.nyx",
        shared_contract("atlas") / "nornyx.agentic_network.lock",
    )
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}

    result = run_foundation("f0", {"injection_enabled": True, "approval_state": "missing"})

    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    assert before == after
    scenario = result.results["scenario"]
    governed = next(variant for variant in scenario["variants"] if variant["id"] == "governed")
    publish = next(
        counter for counter in governed["counters"] if counter["action"] == "publish_external"
    )
    assert publish["attempts"] == 0
    assert publish["completions"] == 0
    assert scenario["restored"] is True


def test_seeded_repeated_sampling_is_variable_and_reproducible() -> None:
    inputs = {"seed": 23, "sample_count": 20, "temperature": 1.1}

    first = run_foundation("F1", inputs)
    second = run_foundation("F1", inputs)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.results["unique_outputs"] > 1
    assert first.results["seeded_fixture"] is True
    assert first.results["exact_text_assertion_recommended"] is False


def test_zero_temperature_fixture_collapses_to_one_output() -> None:
    result = run_foundation("F1", {"temperature": 0, "sample_count": 8})

    assert result.results["unique_outputs"] == 1


def test_context_exercise_preserves_authority_taint_budget_and_schema_steps() -> None:
    result = run_foundation("F2")

    retrieved = next(
        row for row in result.results["context_stack"] if row["layer"] == "retrieved document"
    )
    assert retrieved["authority"] == "informs_only"
    assert retrieved["taint"] == "untrusted"
    assert result.results["untrusted_imperative_detected"] is True
    assert result.results["budget"]["pricing_is_fixture"] is True
    assert result.results["exercise_steps"] == ("compose", "label", "budget", "validate", "route")
    assert result.results["schema_validation"]["valid"] is True


def test_context_exercise_closes_completion_on_budget_or_schema_failure() -> None:
    result = run_foundation(
        "F2",
        {
            "context_window": 128,
            "reserve_output": 120,
            "structured_output": {"answer": "", "sources": [], "confidence": 2},
        },
    )

    assert result.completion_eligible is False
    assert result.results["budget"]["within_budget"] is False
    assert result.results["schema_validation"]["valid"] is False
    assert len(result.results["schema_validation"]["errors"]) == 3


def test_assistant_and_least_privilege_agent_do_not_execute_high_risk_tool() -> None:
    result = run_foundation(
        "F3", {"mode": "least_privilege", "requested_action": "publish_external"}
    )

    assert result.results["assistant"]["counter"] == {
        "action": "publish_external",
        "attempts": 0,
        "completions": 0,
    }
    assert result.results["agent"]["counter"]["attempts"] == 0
    assert result.results["permitted"] is False


def test_overprivileged_agent_visibly_reaches_only_the_inert_callable() -> None:
    result = run_foundation(
        "F3", {"mode": "overprivileged", "requested_action": "publish_external"}
    )

    assert result.results["agent"]["counter"]["attempts"] == 1
    assert result.results["agent"]["counter"]["completions"] == 1
    assert "inert" in result.safety_boundary.lower()
    boundary = next(block for block in result.blocks if block.id == "f3-boundary")
    assert "not a Nornyx decision" in boundary.body


def test_retry_pattern_keeps_one_occurrence_and_distinct_attempts() -> None:
    result = run_foundation("F4", {"pattern": "retry", "max_attempts": 3})

    attempts = result.results["occurrences"]["occ.research.1"]
    assert attempts == ["att.research.1", "att.research.2", "att.research.3"]
    assert len(set(attempts)) == 3
    assert result.results["retry_is_repeated_work"] is False


@pytest.mark.parametrize("pattern", ["linear", "retry", "handoff", "parallel"])
def test_every_runtime_pattern_has_stable_event_identity(pattern: str) -> None:
    result = run_foundation("F4", {"pattern": pattern})

    for event in result.results["timeline"]:
        assert event["occurrence_id"].startswith("occ.")
        assert event["attempt_id"].startswith(("att.", "occ.plan"))


def test_evaluation_workbench_never_turns_missing_repairs_into_green() -> None:
    repairs = {
        "schema_validation": True,
        "authorization": True,
        "timeout_bound": True,
        "retry_idempotency": True,
        "telemetry_required": False,
        "no_hidden_skips": False,
    }
    result = run_foundation("F5", {"repairs": repairs})

    assert result.completion_eligible is False
    assert result.results["delivery_gate"] == "deny"
    assert result.results["failed"] == 2
    assert result.results["skips"] == 0


def test_evaluation_workbench_all_repairs_closes_every_named_case() -> None:
    result = run_foundation("F5")

    assert result.completion_eligible is True
    assert result.results["delivery_gate"] == "allow"
    assert result.results["passed"] == 8
    assert result.results["failed"] == 0


@pytest.mark.parametrize(
    "module_id, inputs",
    [
        ("unknown", {}),
        ("F1", {"sample_count": 1}),
        ("F2", {"structured_output": []}),
        ("F3", {"mode": "root"}),
        ("F4", {"pattern": "distributed"}),
        ("F5", {"repairs": {"pretend_green": True}}),
        ("F1", {"unexpected": True}),
    ],
)
def test_invalid_browser_inputs_fail_closed(module_id: str, inputs: dict[str, object]) -> None:
    with pytest.raises(FoundationInputError):
        run_foundation(module_id, inputs)


def test_foundation_module_never_creates_files_in_contract_directories(tmp_path: Path) -> None:
    del tmp_path  # documents that no temporary path is required by this in-memory module
    roots = (shared_contract("atlas"), shared_contract("ledger"))
    before = {root: sorted(path.relative_to(root) for path in root.rglob("*")) for root in roots}

    for module_id in FOUNDATION_MODULE_IDS:
        run_foundation(module_id)

    after = {root: sorted(path.relative_to(root) for path in root.rglob("*")) for root in roots}
    assert before == after
