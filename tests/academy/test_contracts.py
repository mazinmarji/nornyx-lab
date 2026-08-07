from __future__ import annotations

import hashlib
from pathlib import Path

from nornyx_lab.academy.contracts import (
    FORMATTING_LIMITATION,
    get_contract,
    list_contracts,
    validate_workbench,
)
from nornyx_lab.academy.schemas import (
    ContractMutation,
    ContractWorkbenchRequest,
    EvidenceStatus,
)
from nornyx_lab.engine import repo_root

ROOT = repo_root()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_contract_list_is_derived_from_the_real_atlas_and_ledger_fixtures() -> None:
    summaries = list_contracts()
    assert [item.id for item in summaries] == ["atlas", "ledger"]
    atlas, ledger = summaries
    assert (atlas.name, atlas.profile) == ("NorthstarAtlas", "agentic_network")
    assert (atlas.identity_count, atlas.capability_count, atlas.zone_count, atlas.gate_count) == (
        1,
        3,
        2,
        1,
    )
    assert ledger.identity_count == 4
    assert ledger.capability_count == 8
    assert ledger.gate_count == 4
    assert all(item.lock_status == EvidenceStatus.PASS for item in summaries)


def test_contract_explorer_exposes_source_canonical_graph_controls_and_lock() -> None:
    detail = get_contract("atlas")

    assert detail.source == (ROOT / "contracts/atlas/network.nyx").read_text(encoding="utf-8")
    assert detail.canonical_document["project"]["name"] == "NorthstarAtlas"
    assert detail.canonical_document["agentic_network"]["id"] == "network.northstar_atlas"
    assert detail.summary.lock_status == EvidenceStatus.PASS
    assert not detail.diagnostics
    assert {item["artifact"] for item in detail.generated_controls} == {
        path.name for path in (ROOT / "contracts/atlas/control_artifacts").glob("*.json")
    }
    assert any(
        node.kind == "identity" and node.fields.get("id") == "identity.research_assistant"
        for node in detail.nodes
    )
    assert any(
        edge.kind == "requires_approval"
        and edge.source == "gate:gate.publication_review"
        and edge.target == "approval:agentic_network_authority"
        for edge in detail.edges
    )
    assert any(edge.kind == "allows_transition_to" for edge in detail.edges)
    assert {
        "profile",
        "lock",
        "context",
        "resource",
        "agent",
        "policy_rule",
        "evidence",
    }.issubset({node.kind for node in detail.nodes})
    assert any(edge.kind == "includes_resource" for edge in detail.edges)
    assert any(edge.kind == "scoped_to" for edge in detail.edges)
    assert any(
        node.kind == "lock" and node.fields["status"] == EvidenceStatus.PASS.value
        for node in detail.nodes
    )
    assert detail.formatting_limitation == FORMATTING_LIMITATION
    assert "comments" in detail.formatting_limitation.lower()
    assert "runtime" in detail.assurance_boundary.lower()


def test_ledger_graph_includes_real_delegation_and_handoff_semantics() -> None:
    detail = get_contract("ledger")
    kinds = {node.kind for node in detail.nodes}
    assert {"delegation", "handoff", "membership", "protocol_target"}.issubset(kinds)
    assert any(edge.kind == "delegates_to" for edge in detail.edges)
    assert any(edge.kind == "hands_off_to" for edge in detail.edges)
    assert any(edge.kind == "requires_role" for edge in detail.edges)


def test_noop_workbench_roundtrip_is_real_nornyx_valid_and_lock_clean() -> None:
    request = ContractWorkbenchRequest(contract_id="atlas")
    first = validate_workbench(request)
    second = validate_workbench(request)

    assert first.valid is True
    assert first.lock_status == EvidenceStatus.PASS
    assert first.canonical_document == get_contract("atlas").canonical_document
    assert len(first.generated_controls) == 10
    assert first.source == second.source
    assert first.canonical_document == second.canonical_document
    assert first.nodes == second.nodes
    assert first.edges == second.edges
    assert any(node.kind == "lock" for node in first.nodes)
    assert first.semantic_paths_only is True


def test_semantically_valid_edit_rerenders_controls_and_reports_old_lock_stale() -> None:
    result = validate_workbench(
        ContractWorkbenchRequest(
            contract_id="atlas",
            mutations=(
                ContractMutation(
                    operation="set_project_purpose",
                    target="project.purpose",
                    value="Browser workbench semantic preview.",
                ),
            ),
        )
    )

    assert result.valid is True
    assert result.canonical_document is not None
    assert result.canonical_document["project"]["purpose"] == (
        "Browser workbench semantic preview."
    )
    assert result.lock_status == EvidenceStatus.FAIL
    assert "AN_LOCK_SOURCE_STALE" in {item.code for item in result.diagnostics}
    assert len(result.generated_controls) == 10


def test_invalid_evidence_mutation_returns_real_semantic_path_diagnostics() -> None:
    result = validate_workbench(
        ContractWorkbenchRequest(
            contract_id="atlas",
            mutations=(
                ContractMutation(
                    operation="remove_evidence_field",
                    target="approval_record",
                    value="content_hash",
                ),
            ),
        )
    )

    assert result.valid is False
    codes = {item.code for item in result.diagnostics}
    assert "GOVERNANCE_BLOCK_SCHEMA_INVALID" in codes
    assert "EVIDENCE_SOURCE_VALUE_INVALID" in codes
    assert all("line " not in item.message.lower() for item in result.diagnostics)
    assert result.semantic_paths_only is True


def test_workbench_never_edits_committed_source_lock_or_controls() -> None:
    watched = (
        ROOT / "contracts/atlas/network.nyx",
        ROOT / "contracts/atlas/nornyx.agentic_network.lock",
        ROOT / "contracts/atlas/control_artifacts/capability_matrix.json",
    )
    before = {path: _digest(path) for path in watched}

    validate_workbench(
        ContractWorkbenchRequest(
            contract_id="atlas",
            mutations=(
                ContractMutation(
                    operation="set_zone_share_category",
                    target="zone.public_web",
                    value={"category": "training_preview", "enabled": True},
                ),
                ContractMutation(
                    operation="set_subject_revision",
                    target="agentic_network.subject_revision",
                    value="git:" + "a" * 40,
                ),
            ),
        )
    )

    assert {path: _digest(path) for path in watched} == before


def test_structured_construct_and_rule_forms_return_the_mutated_graph() -> None:
    result = validate_workbench(
        ContractWorkbenchRequest(
            contract_id="atlas",
            mutations=(
                ContractMutation(
                    operation="upsert_construct",
                    target="context",
                    value={
                        "reference": "TrainingContext",
                        "fields": {
                            "include": ["training/**/*.md"],
                            "exclude": ["training/secrets/**"],
                            "authority": ["network.nyx"],
                            "budget_max_tokens": 8000,
                            "budget_reserve_output_tokens": 1000,
                        },
                    },
                ),
                ContractMutation(
                    operation="toggle_context_resource",
                    target="TrainingContext",
                    value={
                        "path": "training/examples/*.md",
                        "placement": "include",
                        "enabled": True,
                    },
                ),
                ContractMutation(
                    operation="toggle_policy_rule",
                    target="AtlasGovernance",
                    value={
                        "effect": "require",
                        "rule": "review_training_exports",
                        "enabled": True,
                    },
                ),
            ),
        )
    )

    assert result.valid is True
    assert result.lock_status == EvidenceStatus.FAIL
    assert result.canonical_document is not None
    context = next(
        item for item in result.canonical_document["contexts"] if item["name"] == "TrainingContext"
    )
    assert context["budget"] == {
        "max_tokens": 8000,
        "reserve_output_tokens": 1000,
    }
    assert "training/examples/*.md" in context["include"]
    assert any(node.kind == "context" and node.label == "TrainingContext" for node in result.nodes)
    assert any(
        node.kind == "resource" and node.label == "training/examples/*.md" for node in result.nodes
    )
    assert any(
        node.kind == "policy_rule" and node.label == "review_training_exports"
        for node in result.nodes
    )


def test_structured_relation_edit_preserves_canonical_nested_endpoints() -> None:
    result = validate_workbench(
        ContractWorkbenchRequest(
            contract_id="ledger",
            mutations=(
                ContractMutation(
                    operation="upsert_construct",
                    target="relation",
                    value={
                        "reference": "relation.notice_advertisement",
                        "fields": {
                            "type": "advertises_capability",
                            "source_kind": "agent_identity",
                            "source_ref": "identity.remediation_agent",
                            "target_kind": "capability",
                            "target_ref": "notify_customer_external",
                            "description": "Visible in the synchronized builder graph.",
                        },
                    },
                ),
            ),
        )
    )

    assert result.valid is True
    assert result.canonical_document is not None
    relation = next(
        item
        for item in result.canonical_document["agentic_network"]["relations"]
        if item["id"] == "relation.notice_advertisement"
    )
    assert relation["source"] == {
        "kind": "agent_identity",
        "ref": "identity.remediation_agent",
    }
    assert relation["target"] == {
        "kind": "capability",
        "ref": "notify_customer_external",
    }
    assert any(
        edge.kind == "advertises_capability"
        and edge.source == "identity:identity.remediation_agent"
        and edge.target == "capability:notify_customer_external"
        for edge in result.edges
    )


def test_construct_form_rejects_fields_that_do_not_map_to_canonical_schema() -> None:
    result = validate_workbench(
        ContractWorkbenchRequest(
            contract_id="atlas",
            mutations=(
                ContractMutation(
                    operation="upsert_construct",
                    target="capability",
                    value={
                        "reference": "search_web",
                        "fields": {"shell_command": "curl example.invalid"},
                    },
                ),
            ),
        )
    )

    assert result.valid is False
    assert {item.code for item in result.diagnostics} == {"WORKBENCH_FIELD_UNSUPPORTED"}
    assert result.nodes


def test_refresh_lock_regenerates_only_the_temporary_copy() -> None:
    lock_path = ROOT / "contracts/atlas/nornyx.agentic_network.lock"
    before = _digest(lock_path)
    result = validate_workbench(
        ContractWorkbenchRequest(
            contract_id="atlas",
            mutations=(
                ContractMutation(
                    operation="set_project_purpose",
                    target="project.purpose",
                    value="Temporary locked builder preview.",
                ),
                ContractMutation(
                    operation="refresh_lock",
                    target="nornyx.agentic_network.lock",
                    value=True,
                ),
            ),
        )
    )

    assert result.valid is True
    assert result.lock_refreshed is True
    assert result.lock_status == EvidenceStatus.PASS
    assert not {item.code for item in result.diagnostics if item.code.startswith("AN_LOCK_")}
    assert _digest(lock_path) == before
