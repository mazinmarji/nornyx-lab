"""Fast checks for dedicated executable replacements of Labs 19, 22, and 23."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nornyx_lab.academy import advanced
from nornyx_lab.academy.advanced import (
    ADVANCED_MODULE_IDS,
    AdvancedInputError,
    run_advanced_module,
)
from nornyx_lab.academy.schemas import RunStatus, StructuredLabRun
from nornyx_lab.contract import shared_contract


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.mark.parametrize("module_id", ADVANCED_MODULE_IDS)
def test_every_advanced_replacement_is_a_typed_complete_browser_run(module_id: str) -> None:
    result = run_advanced_module(module_id)

    assert isinstance(result, StructuredLabRun)
    assert result.module_id == module_id
    assert result.legacy_lab_id == module_id
    assert result.status is RunStatus.COMPLETE
    assert result.completion_eligible is True
    assert result.blocks
    assert result.executable_checks
    assert result.safety_boundary
    assert "terminal" not in result.results


def test_lab_19_uses_real_langgraph_public_runtime_metadata(monkeypatch) -> None:
    graph_module = pytest.importorskip("langgraph.graph")
    compile_calls = 0
    original_compile = graph_module.StateGraph.compile

    def counted_compile(self, *args, **kwargs):
        nonlocal compile_calls
        compile_calls += 1
        return original_compile(self, *args, **kwargs)

    monkeypatch.setattr(graph_module.StateGraph, "compile", counted_compile)
    result = run_advanced_module("19")

    assert result.status is RunStatus.COMPLETE
    assert compile_calls >= 5
    assert result.results["framework"] == {
        "name": "langgraph",
        "version": "1.2.2",
        "adapter": "nornyx-agentic-adapters.langgraph",
        "adapter_version": "0.3.0",
        "actual_execution": True,
        "fallback_used": False,
        "public_metadata": "Runtime.execution_info",
    }


def test_lab_19_exercises_retry_loop_parallel_and_interrupt_resume() -> None:
    result = run_advanced_module("19")
    patterns = result.results["patterns"]

    assert patterns["retry"]["calls"] == 3
    assert patterns["retry"]["distinct_occurrences"] == 1
    assert patterns["retry"]["attempts"] == (1, 2, 3)
    assert patterns["retry"]["event_types"]["runtime_failed"] == 2

    assert patterns["loop"]["calls"] == 2
    assert patterns["loop"]["distinct_occurrences"] == 2
    assert patterns["loop"]["attempts"] == (1,)

    assert patterns["parallel"]["calls"] == {"left": 1, "right": 1}
    assert patterns["parallel"]["distinct_occurrences"] == 2
    assert patterns["parallel"]["attempts"] == (1,)

    resumed = patterns["interrupt_resume"]
    assert resumed["interrupted"] is True
    assert resumed["resumed_answer"] == "approved"
    assert resumed["distinct_occurrences"] == 1
    assert resumed["attempts"] == (1, 2)
    assert resumed["interrupt_recorded_as_failure"] is False

    denial = patterns["authorization_denial"]
    assert denial["decision_effect"] == "deny"
    assert denial["decision_code"] == "CAPABILITY_DENIED"
    assert denial["calls"] == 0
    assert denial["counter"] == {
        "attempts": 0,
        "completions": 0,
        "meaning": "prevented_before_execution",
    }
    assert denial["event_types"]["capability_denied"] == 1
    assert denial["event_types"].get("agent_invoked", 0) == 0

    for pattern in patterns.values():
        assert pattern["actual_framework_execution"] is True
        assert pattern["raw_runtime_ids_exposed"] is False
        assert pattern["evidence"]["status"] == "pass"


def test_lab_19_names_wrapped_unwrapped_and_unsupported_surfaces_exactly() -> None:
    result = run_advanced_module("19")
    coverage = {row["surface"]: row for row in result.results["coverage"]["inventory"]}

    assert coverage["sync_node_invocation"]["status"] == "wrapped"
    assert coverage["sync_node_invocation"]["exercise"] == ("executed_governed_public_metadata")
    assert coverage["graph_topology"]["status"] == "unwrapped"
    assert coverage["graph_topology"]["exercise"] == ("executed_unwrapped_negative_control")
    for surface in (
        "async_node_invocation",
        "remote_or_distributed_execution",
        "subgraph_and_tool_node_internals",
    ):
        assert coverage[surface]["status"] == "unsupported"
    topology = result.results["coverage"]["unwrapped_topology_probe"]
    assert topology["executions"] == 1
    assert topology["nornyx_authorizations"] == 0
    assert topology["nornyx_evidence_events"] == 0
    assert result.results["coverage"]["async_wrapper_probe"] == {
        "action_executed": False,
        "construction_rejected": True,
        "passed": True,
    }


def test_lab_19_is_typed_unavailable_without_the_real_dependency(monkeypatch) -> None:
    original_import = advanced.importlib.import_module

    def without_langgraph(name: str, *args, **kwargs):
        if name.startswith("langgraph"):
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(advanced.importlib, "import_module", without_langgraph)
    result = run_advanced_module("19")

    assert result.status is RunStatus.UNAVAILABLE
    assert result.completion_eligible is False
    assert result.results["framework"]["actual_execution"] is False
    assert result.results["framework"]["fallback_used"] is False
    assert result.diagnostics[0].code == "LANGGRAPH_RUNTIME_UNAVAILABLE"
    assert "UNAVAILABLE" in result.unavailable_reason


def test_lab_22_executes_distinct_identities_delegation_handoff_and_approval() -> None:
    result = run_advanced_module("22")

    identities = {step["identity"] for step in result.results["workflow"]}
    assert identities == {
        "identity.forge_author",
        "identity.forge_reviewer",
        "identity.forge_release_agent",
        "identity.forge_approval_router",
    }
    assert result.title == "Forge Multi-Agent Release Network"
    assert result.results["scenario_id"] == "lab22.forge_release_network"
    assert result.results["interaction"] == "forge-release-network"
    assert result.results["contract"] == {
        "network_id": "network.northstar_forge",
        "source": "ephemeral browser-safe fixture",
        "built_with_public_nornyx_apis": True,
        "repository_mutated": False,
        "lock_verified_before_decision": True,
    }
    assert result.results["delegation"]["code"] == "ALLOWED"
    assert result.results["handoff"]["decision"]["code"] == "ALLOWED"
    assert result.results["handoff"]["counter"]["completions"] == 1
    assert all(row["can_complete_alone"] is False for row in result.results["separation_of_duties"])
    authority = result.results["approvals"]["authority"]
    assert authority == {
        "agent_identity_count": 4,
        "all_agents_non_human": True,
        "no_agent_can_approve": True,
        "human_governance_owner": "human.network_governance_owner",
        "human_owner_is_not_an_agent": True,
        "router_may_request_not_grant": True,
    }


def test_lab_22_keeps_internal_and_combined_approval_semantics_honest() -> None:
    result = run_advanced_module("22")
    approvals = result.results["approvals"]

    assert approvals["merge"]["validation"]["code"] == "ALLOWED"
    assert approvals["merge"]["composition"] == ("application_explicit_conjunction")
    assert approvals["merge"]["authorizer_state_mutated"] is False
    assert approvals["release"]["crossing"]["code"] == "ALLOWED"
    assert approvals["release"]["composition"] == ("nornyx_zone_crossing_request")

    boundary = next(block for block in result.blocks if block.id == "lab-22-boundary")
    assert "does not mutate or unlock" in boundary.body
    assert "CapabilityRequest checks holdings" in boundary.body


def test_lab_22_failure_and_inert_bypass_have_real_counters() -> None:
    result = run_advanced_module("22")
    incident = result.results["incident"]

    denied = incident["author_attempts_merge"]
    assert denied["decision"]["code"] == "CAPABILITY_DENIED"
    assert denied["counter"] == {
        "action": "merge_pull_request",
        "attempts": 0,
        "completions": 0,
        "meaning": "prevented_before_execution",
    }
    missing = incident["release_without_human_approval"]
    assert missing["decision"]["effect"] == "approval_required"
    assert missing["counter"]["attempts"] == 0
    bypass = incident["direct_in_process_bypass"]
    assert bypass["counter"]["attempts"] == 1
    assert bypass["counter"]["completions"] == 1
    assert bypass["nornyx_decisions"] == 0
    assert "uncontrolled" in bypass["coverage"]
    assert result.results["evidence"]["status"] == "pass"


@pytest.mark.parametrize("approval_state", ["missing", "non_human"])
def test_lab_22_invalid_approval_closes_completion(approval_state: str) -> None:
    result = run_advanced_module("22", {"approval_state": approval_state})

    assert result.status is RunStatus.FAILED
    assert result.completion_eligible is False
    merge = next(row for row in result.results["counters"] if row["action"] == "merge_pull_request")
    assert merge["attempts"] == 0
    assert merge["completions"] == 0


def test_lab_23_executes_a_scoped_threat_and_bypass_matrix() -> None:
    result = run_advanced_module("23")
    rows = {row["id"]: row for row in result.results["threat_matrix"]}

    assert rows["TM-23-001"]["decision_code"] == "ALLOWED"
    assert (rows["TM-23-001"]["attempts"], rows["TM-23-001"]["completions"]) == (1, 1)
    assert rows["TM-23-002"]["decision_code"] == "CAPABILITY_DENIED"
    assert (rows["TM-23-002"]["attempts"], rows["TM-23-002"]["completions"]) == (0, 0)
    assert rows["TM-23-003"]["decision_code"] == "CROSSING_APPROVAL_REQUIRED"
    assert rows["TM-23-004"]["decision_code"] == "REVISION_MISMATCH"
    assert rows["TM-23-005"]["decision_code"] == "BYPASS_NO_DECISION"
    assert (rows["TM-23-005"]["attempts"], rows["TM-23-005"]["completions"]) == (1, 1)
    assert "uncontrolled" in rows["TM-23-005"]["coverage"]
    assert rows["TM-23-006"]["decision_effect"] == "indeterminate"
    assert rows["TM-23-006"]["attempts"] is None
    assert rows["TM-23-006"]["completions"] is None


def test_lab_23_mapping_is_specific_and_never_a_certification_claim() -> None:
    result = run_advanced_module("23")
    mappings = result.results["standards_mapping"]

    assert {row["reference"] for row in mappings} == {
        "NIST AI RMF 1.0 — GOVERN 1",
        "ISO/IEC 42001:2023 — clause 9.1",
        "ISO/IEC 27001:2022 Annex A — control 8.15 (Logging)",
    }
    for row in mappings:
        assert row["mapping_status"] == "educational_candidate_not_conformity"
        assert row["certification_claim"] is False
        assert all(
            row[field]
            for field in (
                "mechanism",
                "artifact",
                "evidence",
                "surface",
                "gap",
                "owner",
                "review_cadence",
            )
        )
    assert result.results["mapping_notice"] == {
        "educational_only": True,
        "certification": False,
        "qualified_review_required": True,
    }


def test_lab_23_claim_register_contains_exact_honest_boundaries() -> None:
    result = run_advanced_module("23")
    claims = {claim["status"]: claim for claim in result.results["unsupported_claim_register"]}

    assert set(claims) == {"supported", "unsupported", "indeterminate"}
    assert "direct in-process invocation" in claims["supported"]["uncovered"]
    assert claims["unsupported"]["statement"] == (
        "All agent actions in this process are governed by Nornyx."
    )
    assert "zero Nornyx decisions" in claims["unsupported"]["falsified_by"]
    assert "event truth" in claims["indeterminate"]["uncovered"]
    assert result.results["coverage"]["whole_process_coverage_claimed"] is False
    assert result.results["evidence"]["status"] == "pass"
    assert result.results["evidence"]["limitations"]


def test_lab_23_without_the_direct_negative_control_is_not_completion_eligible() -> None:
    result = run_advanced_module("23", {"include_direct_bypass": False})

    assert result.status is RunStatus.FAILED
    assert result.completion_eligible is False
    assert result.results["checks"]["direct_bypass_demonstrated"] is False


@pytest.mark.parametrize("module_id", ADVANCED_MODULE_IDS)
def test_advanced_runs_are_deterministic_and_do_not_expose_local_paths(module_id: str) -> None:
    first = run_advanced_module(module_id)
    second = run_advanced_module(module_id)

    first_json = first.model_dump(mode="json")
    second_json = second.model_dump(mode="json")
    assert first_json == second_json
    rendered = json.dumps(first_json, sort_keys=True)
    assert str(Path.cwd()) not in rendered
    assert "AppData" not in rendered
    assert "\\\\" not in rendered


def test_all_three_replacements_leave_committed_contract_trees_unchanged() -> None:
    roots = (shared_contract("atlas"), shared_contract("ledger"))
    before = {root.name: _tree_digest(root) for root in roots}

    for module_id in ADVANCED_MODULE_IDS:
        run_advanced_module(module_id)

    after = {root.name: _tree_digest(root) for root in roots}
    assert before == after


@pytest.mark.parametrize(
    "module_id, inputs",
    [
        ("18", {}),
        ("", {}),
        ("lab-19", {}),
        ("19", {"mode": "modeled"}),
        ("22", {"approval_state": "agent"}),
        ("22", {"include_inert_bypass": "yes"}),
        ("23", {"include_direct_bypass": 1}),
        ("23", {"unexpected": True}),
    ],
)
def test_advanced_inputs_fail_closed(module_id: str, inputs: dict[str, object]) -> None:
    with pytest.raises(AdvancedInputError):
        run_advanced_module(module_id, inputs)


def test_advanced_input_must_be_a_mapping() -> None:
    with pytest.raises(AdvancedInputError):
        run_advanced_module("22", ["not", "an", "object"])  # type: ignore[arg-type]
