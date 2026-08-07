"""Read-only contract explorer and isolated visual-workbench service.

The checked-in Atlas and Ledger ``.nyx`` contracts remain authoritative.  This
module parses and checks them through Nornyx's published Python APIs, reads the
committed generated controls and lock, and derives a UI graph from the canonical
document.  Workbench edits are applied only to a temporary copy, reparsed, and
validated again; comments and source formatting are intentionally not promised.
"""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from nornyx.agentic import (
    build_agentic_network_lock,
    check_document,
    compose_document_governance,
    evaluate_document_governance,
    load_agentic_network_lock,
    load_nyx,
    registry_for_contract,
    render_agentic_network_artifacts,
    verify_agentic_network_lock,
    write_agentic_network_lock,
)
from nornyx.governance import GovernanceError

from nornyx_lab.constants import LAB_AS_OF
from nornyx_lab.contract import shared_contract

from .schemas import (
    ContractDetail,
    ContractEdge,
    ContractMutation,
    ContractNode,
    ContractSummary,
    ContractValidation,
    ContractWorkbenchRequest,
    EvidenceFinding,
    EvidenceStatus,
)

CONTRACT_IDS = ("atlas", "ledger")
FORMATTING_LIMITATION = (
    "The source view is the checked-in text. Workbench output is a semantic YAML rendering of "
    "the canonical dictionary: comments, quoting choices, blank lines, key layout, and source "
    "line positions are not preserved or reported. Diagnostics use semantic paths only."
)
ASSURANCE_BOUNDARY = (
    "The explorer reports declarations, generated controls, and lock consistency. It does not "
    "prove that a runtime loads them, that an adapter covers every path, or that recorded events "
    "are true."
)


class ContractWorkbenchError(ValueError):
    """A bounded workbench operation could not be applied to the canonical dict."""

    def __init__(self, code: str, message: str, *, path: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def _contract_root(contract_id: str) -> Path:
    if contract_id not in CONTRACT_IDS:
        raise KeyError(f"unknown academy contract: {contract_id}")
    root = shared_contract(contract_id)
    if not (root / "network.nyx").is_file():
        raise FileNotFoundError(f"academy contract fixture is missing: {contract_id}")
    return root


def _finding_from_diagnostic(item: Any) -> EvidenceFinding:
    level = str(getattr(item, "level", "warning"))
    code = str(getattr(item, "code", "NORNYX_DIAGNOSTIC"))
    message = str(getattr(item, "message", "Nornyx returned a diagnostic."))
    path_value = getattr(item, "path", None)
    return EvidenceFinding(
        status=(
            EvidenceStatus.FAIL
            if level == "error"
            else EvidenceStatus.UNKNOWN
            if level == "warning"
            else EvidenceStatus.PASS
        ),
        code=code,
        message=message,
        path=str(path_value) if path_value is not None else None,
        missing_fields=(str(path_value),)
        if code.startswith("MISSING_") and path_value is not None
        else (),
    )


def _error_finding(code: str, message: str, *, path: str | None = None) -> EvidenceFinding:
    return EvidenceFinding(
        status=EvidenceStatus.FAIL,
        code=code,
        message=message,
        path=path,
    )


def _validate_document(
    contract_path: Path,
) -> tuple[dict[str, Any] | None, Any | None, list[Any], EvidenceFinding | None]:
    """Parse, compose, and evaluate with the same public APIs as Nornyx."""

    try:
        registry = registry_for_contract(contract_path)
        document = load_nyx(contract_path)
        diagnostics = list(check_document(document))
        composition = compose_document_governance(document, registry=registry)
        if composition is None:
            diagnostics.append(
                _SyntheticDiagnostic(
                    "error",
                    "PROFILE_MISSING",
                    "The contract does not resolve a governance profile.",
                    "project.profile",
                )
            )
        else:
            contributed = {item.block for item in (composition.block_schemas or ())}
            diagnostics = [
                item
                for item in diagnostics
                if not (
                    getattr(item, "code", None) == "UNKNOWN_TOP_LEVEL_BLOCK"
                    and getattr(item, "path", None) in contributed
                )
            ]
            diagnostics.extend(
                evaluate_document_governance(
                    document,
                    registry=registry,
                    as_of=LAB_AS_OF,
                    document_root=contract_path.parent,
                )
            )
        return document, composition, diagnostics, None
    except GovernanceError as exc:
        diagnostics = list(exc.diagnostics)
        return None, None, diagnostics, None
    except Exception as exc:  # parser and filesystem failures become typed diagnostics
        return (
            None,
            None,
            [],
            _error_finding(
                "CONTRACT_PARSE_FAILED",
                f"Nornyx could not parse the contract ({type(exc).__name__}).",
                path="network.nyx",
            ),
        )


class _SyntheticDiagnostic:
    def __init__(self, level: str, code: str, message: str, path: str | None = None) -> None:
        self.level = level
        self.code = code
        self.message = message
        self.path = path


def _lock_findings(
    root: Path,
    document: dict[str, Any] | None,
    composition: Any | None,
) -> tuple[EvidenceStatus, tuple[EvidenceFinding, ...]]:
    if document is None or composition is None:
        return (
            EvidenceStatus.UNKNOWN,
            (
                EvidenceFinding(
                    status=EvidenceStatus.UNKNOWN,
                    code="LOCK_NOT_EVALUATED",
                    message="The lock cannot be evaluated until the contract composes successfully.",
                ),
            ),
        )
    try:
        lock_payload = load_agentic_network_lock(root / "nornyx.agentic_network.lock")
        diagnostics = verify_agentic_network_lock(
            lock_payload,
            document,
            composition,
            artifacts_dir=root / "control_artifacts",
        )
    except Exception as exc:
        return (
            EvidenceStatus.FAIL,
            (
                _error_finding(
                    "LOCK_CHECK_FAILED",
                    f"Nornyx could not read or verify the lock ({type(exc).__name__}).",
                    path="nornyx.agentic_network.lock",
                ),
            ),
        )
    findings = tuple(_finding_from_diagnostic(item) for item in diagnostics)
    return (EvidenceStatus.FAIL if diagnostics else EvidenceStatus.PASS, findings)


def _committed_controls(root: Path) -> tuple[dict[str, Any], ...]:
    controls: list[dict[str, Any]] = []
    for path in sorted((root / "control_artifacts").glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            payload = {
                "error": type(exc).__name__,
                "message": "The committed generated control could not be read as JSON.",
            }
        controls.append({"artifact": path.name, "document": payload})
    return tuple(controls)


def _rendered_controls(
    document: dict[str, Any],
    composition: Any,
) -> tuple[dict[str, Any], ...]:
    rendered = render_agentic_network_artifacts(document, composition)
    return _decoded_controls(rendered)


def _decoded_controls(rendered: dict[str, bytes]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "artifact": name,
            "document": json.loads(raw.decode("utf-8")),
        }
        for name, raw in sorted(rendered.items())
    )


def _refresh_temporary_lock(
    root: Path,
    document: dict[str, Any],
    composition: Any,
    rendered: dict[str, bytes],
) -> None:
    """Refresh only the copied controls and lock with Nornyx-generated bytes."""

    artifacts = root / "control_artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    for name, raw in rendered.items():
        target = artifacts / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    lock_payload = build_agentic_network_lock(document, composition)
    write_agentic_network_lock(lock_payload, root / "nornyx.agentic_network.lock")


def _summary(
    contract_id: str,
    document: dict[str, Any],
    lock_status: EvidenceStatus,
) -> ContractSummary:
    project = document.get("project", {})
    network = document.get("agentic_network", {})
    return ContractSummary(
        id=contract_id,
        name=str(project.get("name", contract_id.title())) if isinstance(project, dict) else contract_id,
        profile=str(project.get("profile", "")) if isinstance(project, dict) else "",
        identity_count=len(document.get("agent_identities", []) or []),
        capability_count=len(document.get("capabilities", []) or []),
        zone_count=len(network.get("trust_zones", []) or []) if isinstance(network, dict) else 0,
        gate_count=len(network.get("network_gates", []) or []) if isinstance(network, dict) else 0,
        lock_status=lock_status,
    )


def _map_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _graph(
    document: dict[str, Any],
    *,
    lock_status: EvidenceStatus = EvidenceStatus.UNKNOWN,
) -> tuple[tuple[ContractNode, ...], tuple[ContractEdge, ...]]:
    nodes: dict[str, ContractNode] = {}
    edges: dict[tuple[str, str, str, str], ContractEdge] = {}

    def node_id(kind: str, ref: str) -> str:
        aliases = {
            "agent_identity": "identity",
            "identity": "identity",
            "trust_zone": "zone",
            "network_gate": "gate",
        }
        return f"{aliases.get(kind, kind)}:{ref}"

    def add_node(
        kind: str,
        ref: str,
        *,
        label: str | None = None,
        detail: str = "",
        fields: dict[str, Any] | None = None,
    ) -> str:
        key = node_id(kind, ref)
        if key not in nodes:
            nodes[key] = ContractNode(
                id=key,
                kind=kind,
                label=label or ref,
                detail=detail,
                fields=copy.deepcopy(fields or {}),
            )
        return key

    def ensure_ref(kind: str, ref: Any) -> str:
        text = str(ref)
        return add_node(kind, text, label=text)

    def add_edge(source: str, target: str, kind: str, label: str = "") -> None:
        key = (source, target, kind, label)
        edges.setdefault(key, ContractEdge(source=source, target=target, kind=kind, label=label))

    project = document.get("project", {})
    if isinstance(project, dict):
        project_name = str(project.get("name", "project"))
        project_node = add_node(
            "project",
            project_name,
            detail=str(project.get("purpose", "")),
            fields=project,
        )
    else:
        project_node = add_node("project", "project")

    if isinstance(project, dict):
        profile_name = str(project.get("profile", "unresolved"))
        profile_pack = project.get("profile_pack", {})
        profile_fields = (
            copy.deepcopy(profile_pack) if isinstance(profile_pack, dict) else {}
        )
        profile_fields["profile"] = profile_name
        profile_node = add_node(
            "profile",
            profile_name,
            detail=str(profile_fields.get("version", "")),
            fields=profile_fields,
        )
        add_edge(project_node, profile_node, "uses_profile")

    network_for_lock = document.get("agentic_network", {})
    lock_fields = {
        "status": lock_status.value,
        "subject_revision": (
            network_for_lock.get("subject_revision")
            if isinstance(network_for_lock, dict)
            else None
        ),
    }
    lock_node = add_node(
        "lock",
        "nornyx.agentic_network.lock",
        detail=lock_status.value,
        fields=lock_fields,
    )
    add_edge(project_node, lock_node, "binds_lock")

    contexts: dict[str, str] = {}
    for context in _map_items(document.get("contexts")):
        ref = str(context.get("name", "unnamed-context"))
        context_node = add_node("context", ref, fields=context)
        contexts[ref] = context_node
        add_edge(project_node, context_node, "declares_context")
        for placement, edge_kind in (
            ("include", "includes_resource"),
            ("exclude", "excludes_resource"),
            ("authority", "trusts_as_authority"),
        ):
            for path in context.get(placement, []) or []:
                path_text = str(path)
                resource_node = add_node(
                    "resource",
                    f"{ref}:{placement}:{path_text}",
                    label=path_text,
                    detail=placement,
                    fields={"context_ref": ref, "placement": placement, "path": path_text},
                )
                add_edge(context_node, resource_node, edge_kind)

    policies: dict[str, str] = {}
    for policy in _map_items(document.get("policies")):
        ref = str(policy.get("name", "unnamed-policy"))
        policies[ref] = add_node("policy", ref, fields=policy)
        add_edge(project_node, policies[ref], "declares_policy")
        for effect in ("deny", "require"):
            for rule in policy.get(effect, []) or []:
                rule_text = str(rule)
                rule_node = add_node(
                    "policy_rule",
                    f"{ref}:{effect}:{rule_text}",
                    label=rule_text,
                    detail=effect,
                    fields={"policy_ref": ref, "effect": effect, "rule": rule_text},
                )
                add_edge(policies[ref], rule_node, effect)

    agents: dict[str, str] = {}
    for agent in _map_items(document.get("agents")):
        ref = str(agent.get("name", "unnamed-agent"))
        agent_node = add_node(
            "agent",
            ref,
            detail=str(agent.get("role", "")),
            fields=agent,
        )
        agents[ref] = agent_node
        add_edge(project_node, agent_node, "declares_agent")
        policy_ref = str(agent.get("policy", ""))
        if policy_ref:
            add_edge(
                agent_node,
                policies.get(policy_ref, ensure_ref("policy", policy_ref)),
                "governed_by",
            )

    approvals: dict[str, str] = {}
    for approval in _map_items(document.get("approvals")):
        ref = str(approval.get("name", approval.get("id", "unnamed-approval")))
        approval_node = add_node("approval", ref, fields=approval)
        approvals[ref] = approval_node
        add_edge(project_node, approval_node, "declares_approval")
        for role in approval.get("required_roles", []) or []:
            role_node = ensure_ref("human_role", role)
            add_edge(approval_node, role_node, "requires_role")

    evidence_nodes: dict[str, str] = {}
    governance_evidence = document.get("governance_evidence", {})
    if isinstance(governance_evidence, dict):
        for record in _map_items(governance_evidence.get("records")):
            ref = str(record.get("id", "unnamed-evidence"))
            evidence_nodes[ref] = add_node(
                "evidence",
                ref,
                detail=str(record.get("type", "")),
                fields=record,
            )
            add_edge(project_node, evidence_nodes[ref], "declares_evidence")
        for record in _map_items(governance_evidence.get("records")):
            ref = str(record.get("id", "unnamed-evidence"))
            for dependency in record.get("dependencies", []) or []:
                add_edge(
                    evidence_nodes.get(ref, ensure_ref("evidence", ref)),
                    evidence_nodes.get(
                        str(dependency), ensure_ref("evidence", dependency)
                    ),
                    "depends_on_evidence",
                )

    for approval in _map_items(document.get("approvals")):
        ref = str(approval.get("name", approval.get("id", "unnamed-approval")))
        for evidence in approval.get("required_evidence", []) or []:
            add_edge(
                approvals.get(ref, ensure_ref("approval", ref)),
                evidence_nodes.get(str(evidence), ensure_ref("evidence", evidence)),
                "requires_evidence",
            )

    capabilities: dict[str, str] = {}
    for capability in _map_items(document.get("capabilities")):
        ref = str(capability.get("name", "unnamed-capability"))
        capability_node = add_node(
            "capability",
            ref,
            detail=", ".join(str(item) for item in capability.get("actions", []) or []),
            fields=capability,
        )
        capabilities[ref] = capability_node
        add_edge(project_node, capability_node, "declares_capability")
        for context_ref in capability.get("scope_refs", []) or []:
            add_edge(
                capability_node,
                contexts.get(str(context_ref), ensure_ref("context", context_ref)),
                "scoped_to",
            )
        for gate in capability.get("required_gate_refs", []) or []:
            add_edge(capability_node, ensure_ref("gate", gate), "requires_gate")
        for approval in capability.get("required_approval_refs", []) or []:
            add_edge(capability_node, approvals.get(str(approval), ensure_ref("approval", approval)), "requires_approval")
        for evidence in capability.get("required_evidence_refs", []) or []:
            add_edge(capability_node, evidence_nodes.get(str(evidence), ensure_ref("evidence", evidence)), "requires_evidence")

    identities: dict[str, str] = {}
    for identity in _map_items(document.get("agent_identities")):
        ref = str(identity.get("id", "unnamed-identity"))
        identity_node = add_node(
            "identity",
            ref,
            detail=str(identity.get("role_ref", "")),
            fields=identity,
        )
        identities[ref] = identity_node
        add_edge(project_node, identity_node, "declares_identity")
        role_ref = str(identity.get("role_ref", ""))
        if role_ref:
            add_edge(
                identity_node,
                agents.get(role_ref, ensure_ref("agent", role_ref)),
                "implements_agent",
            )
        for capability in identity.get("capability_refs", []) or []:
            add_edge(
                identity_node,
                capabilities.get(str(capability), ensure_ref("capability", capability)),
                "holds_capability",
            )

    network = document.get("agentic_network", {})
    if not isinstance(network, dict):
        network = {}
    network_ref = str(network.get("id", "agentic_network"))
    network_node = add_node("network", network_ref, fields=network)
    add_edge(project_node, network_node, "declares_network")

    zones: dict[str, str] = {}
    for zone in _map_items(network.get("trust_zones")):
        ref = str(zone.get("id", "unnamed-zone"))
        zone_node = add_node(
            "trust_zone",
            ref,
            detail=str(zone.get("classification", "")),
            fields=zone,
        )
        zones[ref] = zone_node
        add_edge(network_node, zone_node, "contains_zone")
    for zone in _map_items(network.get("trust_zones")):
        source_ref = str(zone.get("id", "unnamed-zone"))
        for target in zone.get("allowed_transition_targets", []) or []:
            add_edge(
                zones.get(source_ref, ensure_ref("trust_zone", source_ref)),
                zones.get(str(target), ensure_ref("trust_zone", target)),
                "allows_transition_to",
            )

    gates: dict[str, str] = {}
    for gate in _map_items(network.get("network_gates")):
        ref = str(gate.get("id", "unnamed-gate"))
        gate_node = add_node(
            "gate",
            ref,
            detail=", ".join(str(item) for item in gate.get("action_classes", []) or []),
            fields=gate,
        )
        gates[ref] = gate_node
        add_edge(network_node, gate_node, "declares_gate")
        for source in gate.get("source_zone_refs", []) or []:
            add_edge(zones.get(str(source), ensure_ref("trust_zone", source)), gate_node, "egresses_through")
        for target in gate.get("target_zone_refs", []) or []:
            add_edge(gate_node, zones.get(str(target), ensure_ref("trust_zone", target)), "enters_zone")
        for policy in gate.get("required_policy_refs", []) or []:
            add_edge(gate_node, policies.get(str(policy), ensure_ref("policy", policy)), "requires_policy")
        for approval in gate.get("required_approval_refs", []) or []:
            add_edge(gate_node, approvals.get(str(approval), ensure_ref("approval", approval)), "requires_approval")
        for evidence in gate.get("required_evidence_refs", []) or []:
            add_edge(gate_node, evidence_nodes.get(str(evidence), ensure_ref("evidence", evidence)), "requires_evidence")

    for membership in _map_items(network.get("memberships")):
        ref = str(membership.get("id", "unnamed-membership"))
        membership_node = add_node("membership", ref, fields=membership)
        identity_ref = str(membership.get("identity_ref", ""))
        zone_ref = str(membership.get("trust_zone_ref", ""))
        add_edge(
            identities.get(identity_ref, ensure_ref("identity", identity_ref)),
            membership_node,
            "has_membership",
        )
        add_edge(
            membership_node,
            zones.get(zone_ref, ensure_ref("trust_zone", zone_ref)),
            "member_of",
        )
        for capability in membership.get("capability_refs", []) or []:
            add_edge(
                membership_node,
                capabilities.get(str(capability), ensure_ref("capability", capability)),
                "authorizes_capability",
            )

    for protocol in _map_items(network.get("protocol_targets")):
        ref = str(protocol.get("id", "unnamed-protocol"))
        protocol_node = add_node(
            "protocol_target",
            ref,
            detail=str(protocol.get("execution_mode", "")),
            fields=protocol,
        )
        add_edge(network_node, protocol_node, "declares_protocol_target")
        for identity in protocol.get("identity_refs", []) or []:
            add_edge(identities.get(str(identity), ensure_ref("identity", identity)), protocol_node, "may_target_protocol")

    revocations: dict[str, str] = {}
    for revocation in _map_items(network.get("revocations")):
        ref = str(revocation.get("id", "unnamed-revocation"))
        revocation_node = add_node(
            "revocation",
            ref,
            detail=str(revocation.get("reason", "")),
            fields=revocation,
        )
        revocations[ref] = revocation_node
        add_edge(network_node, revocation_node, "declares_revocation")
        target = revocation.get("target", {})
        if isinstance(target, dict):
            target_kind = str(target.get("kind", "revocation_target"))
            target_ref = next(
                (
                    str(value)
                    for key, value in target.items()
                    if key != "kind" and key.endswith("_ref")
                ),
                "",
            )
            aliases = {
                "agent_identity": "identity",
                "capability_assignment": "capability",
                "approval_record": "evidence",
            }
            if target_ref:
                add_edge(
                    revocation_node,
                    ensure_ref(aliases.get(target_kind, target_kind), target_ref),
                    "revokes",
                )

    for delegation in _map_items(network.get("delegations")):
        ref = str(delegation.get("id", "unnamed-delegation"))
        delegation_node = add_node("delegation", ref, fields=delegation)
        source_ref = str(delegation.get("delegator_ref", ""))
        target_ref = str(delegation.get("delegate_ref", ""))
        add_edge(identities.get(source_ref, ensure_ref("identity", source_ref)), delegation_node, "delegates")
        add_edge(
            delegation_node,
            identities.get(target_ref, ensure_ref("identity", target_ref)),
            "delegates_to",
            str(delegation.get("capability_ref", "")),
        )

    for handoff in _map_items(network.get("handoffs")):
        ref = str(handoff.get("id", "unnamed-handoff"))
        handoff_node = add_node("handoff", ref, fields=handoff)
        source_ref = str(handoff.get("from_identity_ref", ""))
        target_ref = str(handoff.get("to_identity_ref", ""))
        add_edge(identities.get(source_ref, ensure_ref("identity", source_ref)), handoff_node, "hands_off")
        add_edge(handoff_node, identities.get(target_ref, ensure_ref("identity", target_ref)), "hands_off_to")

    revocation_sources: tuple[tuple[str, list[dict[str, Any]], str], ...] = (
        ("identity", _map_items(document.get("agent_identities")), "id"),
        ("membership", _map_items(network.get("memberships")), "id"),
        ("delegation", _map_items(network.get("delegations")), "id"),
        ("handoff", _map_items(network.get("handoffs")), "id"),
    )
    for kind, records, key in revocation_sources:
        for record in records:
            source_ref = str(record.get(key, ""))
            for revocation_ref in record.get("revocation_refs", []) or []:
                add_edge(
                    ensure_ref(kind, source_ref),
                    revocations.get(
                        str(revocation_ref),
                        ensure_ref("revocation", revocation_ref),
                    ),
                    "subject_to_revocation",
                )

    relation_kind_alias = {
        "agent_identity": "identity",
        "capability": "capability",
        "human_role": "human_role",
        "trust_zone": "trust_zone",
        "network_gate": "gate",
        "approval_record": "evidence",
    }
    for relation in _map_items(network.get("relations")):
        source = relation.get("source", {})
        target = relation.get("target", {})
        if not isinstance(source, dict) or not isinstance(target, dict):
            continue
        source_kind = relation_kind_alias.get(str(source.get("kind")), str(source.get("kind")))
        target_kind = relation_kind_alias.get(str(target.get("kind")), str(target.get("kind")))
        source_ref = str(source.get("ref", ""))
        target_ref = str(target.get("ref", ""))
        add_edge(
            ensure_ref(source_kind, source_ref),
            ensure_ref(target_kind, target_ref),
            str(relation.get("type", "relation")),
            str(relation.get("id", "")),
        )

    return (
        tuple(nodes[key] for key in sorted(nodes)),
        tuple(edges[key] for key in sorted(edges)),
    )


def list_contracts() -> tuple[ContractSummary, ...]:
    """List the two real, committed academy contracts."""

    summaries: list[ContractSummary] = []
    for contract_id in CONTRACT_IDS:
        root = _contract_root(contract_id)
        document, composition, _, parse_failure = _validate_document(root / "network.nyx")
        if document is None:
            # This should make fixture corruption visible rather than presenting
            # a plausible empty contract.
            raise RuntimeError(parse_failure.message if parse_failure else f"{contract_id} is invalid")
        lock_status, _ = _lock_findings(root, document, composition)
        summaries.append(_summary(contract_id, document, lock_status))
    return tuple(summaries)


def get_contract(contract_id: str) -> ContractDetail:
    """Explore source, canonical semantics, graph, controls, and lock status."""

    root = _contract_root(contract_id)
    source = (root / "network.nyx").read_text(encoding="utf-8")
    document, composition, raw_diagnostics, parse_failure = _validate_document(root / "network.nyx")
    if document is None:
        raise RuntimeError(parse_failure.message if parse_failure else f"{contract_id} does not parse")
    lock_status, lock_findings = _lock_findings(root, document, composition)
    diagnostics = tuple(_finding_from_diagnostic(item) for item in raw_diagnostics) + lock_findings
    nodes, edges = _graph(document, lock_status=lock_status)
    return ContractDetail(
        summary=_summary(contract_id, document, lock_status),
        source=source,
        canonical_document=document,
        nodes=nodes,
        edges=edges,
        generated_controls=_committed_controls(root),
        diagnostics=diagnostics,
        formatting_limitation=FORMATTING_LIMITATION,
        assurance_boundary=ASSURANCE_BOUNDARY,
    )


def _find(items: Iterable[dict[str, Any]], field: str, target: str, *, kind: str) -> dict[str, Any]:
    for item in items:
        if item.get(field) == target:
            return item
    raise ContractWorkbenchError(
        "WORKBENCH_TARGET_UNKNOWN",
        f"No {kind} named {target!r} exists in the contract.",
        path=target,
    )


def _toggle(values: list[Any], item: str, enabled: bool | None) -> None:
    present = item in values
    should_enable = not present if enabled is None else enabled
    if should_enable and not present:
        values.append(item)
    elif not should_enable and present:
        values.remove(item)
    values.sort(key=str)


def _value_switch(value: Any, *, noun: str) -> tuple[str, bool | None]:
    if isinstance(value, str) and value:
        return value, None
    if isinstance(value, dict):
        item = value.get(noun) or value.get(f"{noun}_ref")
        enabled = value.get("enabled")
        if not isinstance(item, str) or not item:
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                f"The {noun} mutation needs a non-empty {noun} or {noun}_ref string.",
            )
        if enabled is not None and not isinstance(enabled, bool):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "The optional enabled field must be boolean.",
            )
        return item, enabled
    raise ContractWorkbenchError(
        "WORKBENCH_VALUE_INVALID",
        f"The {noun} mutation value must be a string or an object.",
    )


_CONSTRUCT_LOCATIONS: dict[str, tuple[str, str]] = {
    "context": ("contexts", "name"),
    "agent": ("agents", "name"),
    "policy": ("policies", "name"),
    "capability": ("capabilities", "name"),
    "identity": ("agent_identities", "id"),
    "approval": ("approvals", "name"),
    "evidence": ("governance_evidence.records", "id"),
    "trust_zone": ("agentic_network.trust_zones", "id"),
    "membership": ("agentic_network.memberships", "id"),
    "protocol_target": ("agentic_network.protocol_targets", "id"),
    "gate": ("agentic_network.network_gates", "id"),
    "revocation": ("agentic_network.revocations", "id"),
    "delegation": ("agentic_network.delegations", "id"),
    "handoff": ("agentic_network.handoffs", "id"),
    "relation": ("agentic_network.relations", "id"),
}

_CONSTRUCT_FIELDS: dict[str, frozenset[str]] = {
    "context": frozenset(
        {
            "include",
            "exclude",
            "authority",
            "budget",
            "budget_max_tokens",
            "budget_reserve_output_tokens",
        }
    ),
    "agent": frozenset({"role", "policy"}),
    "policy": frozenset({"deny", "require"}),
    "capability": frozenset(
        {
            "actions",
            "risk",
            "scope_type",
            "scope_refs",
            "delegable",
            "max_delegation_depth",
            "required_gate_refs",
            "required_approval_refs",
            "required_evidence_refs",
        }
    ),
    "identity": frozenset(
        {
            "role_ref",
            "identity_class",
            "namespace",
            "subject",
            "framework_bindings",
            "framework",
            "framework_agent_key",
            "capability_refs",
            "status",
            "valid_from",
            "expires_at",
            "revocation_refs",
            "authority",
            "can_approve",
        }
    ),
    "approval": frozenset(
        {
            "required_roles",
            "eligible_roles",
            "denied_actor_types",
            "required_evidence",
            "required_for",
            "timing",
            "accountable_authority",
            "revision_binding",
            "revision_kind",
            "revision",
            "exact_revision",
            "invalidation_conditions",
            "expires_at",
        }
    ),
    "evidence": frozenset(
        {
            "type",
            "schema_id",
            "producer",
            "producer_id",
            "producer_type",
            "artifact",
            "content_hash",
            "subject_revision",
            "tool",
            "tool_name",
            "tool_version",
            "generated_at",
            "expires_at",
            "status",
            "dependencies",
        }
    ),
    "trust_zone": frozenset(
        {
            "classification",
            "allowed_transition_targets",
            "share_allowlist",
            "never_share",
            "ingress_gate_refs",
            "egress_gate_refs",
        }
    ),
    "membership": frozenset(
        {
            "identity_ref",
            "trust_zone_ref",
            "capability_refs",
            "status",
            "valid_from",
            "expires_at",
            "revocation_refs",
        }
    ),
    "protocol_target": frozenset(
        {
            "protocol",
            "version",
            "execution_mode",
            "live_connector_execution",
            "identity_refs",
            "source_membership_refs",
            "source_zone_ref",
            "capability_refs",
            "trust_zone_ref",
            "share",
            "never_share",
            "required_gate_refs",
            "required_approval_refs",
            "required_evidence_refs",
        }
    ),
    "gate": frozenset(
        {
            "action_classes",
            "source_zone_refs",
            "target_zone_refs",
            "required_policy_refs",
            "required_approval_refs",
            "required_evidence_refs",
        }
    ),
    "revocation": frozenset(
        {
            "target",
            "target_kind",
            "target_ref",
            "principal_type",
            "capability_ref",
            "effective_at",
            "reason",
            "required_approval_refs",
            "required_evidence_refs",
        }
    ),
    "delegation": frozenset(
        {
            "delegator_ref",
            "delegate_ref",
            "capability_ref",
            "purpose",
            "actions",
            "scope_refs",
            "status",
            "valid_from",
            "expires_at",
            "max_depth",
            "current_depth",
            "onward_delegation",
            "parent_delegation_ref",
            "source_zone_ref",
            "target_zone_ref",
            "required_gate_refs",
            "required_policy_refs",
            "required_approval_refs",
            "required_evidence_refs",
            "revocation_refs",
        }
    ),
    "handoff": frozenset(
        {
            "from_identity_ref",
            "to_identity_ref",
            "purpose",
            "mission_ref",
            "from_zone_ref",
            "to_zone_ref",
            "required_capability_refs",
            "delegation_refs",
            "shared_context",
            "never_share",
            "status",
            "superseded_by_ref",
            "valid_from",
            "expires_at",
            "required_gate_refs",
            "required_approval_refs",
            "required_evidence_refs",
            "revocation_refs",
        }
    ),
    "relation": frozenset(
        {
            "type",
            "source",
            "source_kind",
            "source_ref",
            "target",
            "target_kind",
            "target_ref",
            "delegation_ref",
            "handoff_ref",
            "protocol_target_ref",
            "share_categories",
            "description",
        }
    ),
}

_LIST_FIELDS = frozenset(
    {
        "include",
        "exclude",
        "authority",
        "deny",
        "require",
        "actions",
        "scope_refs",
        "capability_refs",
        "revocation_refs",
        "required_gate_refs",
        "required_approval_refs",
        "required_evidence_refs",
        "required_roles",
        "eligible_roles",
        "denied_actor_types",
        "required_evidence",
        "required_for",
        "invalidation_conditions",
        "dependencies",
        "allowed_transition_targets",
        "share_allowlist",
        "never_share",
        "ingress_gate_refs",
        "egress_gate_refs",
        "identity_refs",
        "source_membership_refs",
        "share",
        "action_classes",
        "source_zone_refs",
        "target_zone_refs",
        "required_policy_refs",
        "required_capability_refs",
        "delegation_refs",
        "shared_context",
        "share_categories",
    }
)


def _construct_collection(
    document: dict[str, Any], kind: str
) -> tuple[list[Any], str]:
    if kind not in _CONSTRUCT_LOCATIONS:
        raise ContractWorkbenchError(
            "WORKBENCH_CONSTRUCT_UNSUPPORTED",
            f"{kind!r} is not a canonical construct supported by this workbench.",
            path=kind,
        )
    path, key = _CONSTRUCT_LOCATIONS[kind]
    parent: dict[str, Any] = document
    parts = path.split(".")
    for part in parts[:-1]:
        child = parent.get(part)
        if not isinstance(child, dict):
            raise ContractWorkbenchError(
                "WORKBENCH_SHAPE_INVALID",
                f"The canonical {'.'.join(parts[:-1])} block is missing.",
                path=".".join(parts[:-1]),
            )
        parent = child
    collection = parent.setdefault(parts[-1], [])
    if not isinstance(collection, list):
        raise ContractWorkbenchError(
            "WORKBENCH_SHAPE_INVALID",
            f"The canonical {path} collection is not a list.",
            path=path,
        )
    return collection, key


def _normalise_construct_fields(kind: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContractWorkbenchError(
            "WORKBENCH_VALUE_INVALID",
            "Construct fields must be supplied by the structured form.",
        )
    unknown = set(raw) - _CONSTRUCT_FIELDS[kind]
    if unknown:
        names = ", ".join(sorted(str(item) for item in unknown))
        raise ContractWorkbenchError(
            "WORKBENCH_FIELD_UNSUPPORTED",
            f"The {kind} form does not map canonical field(s): {names}.",
            path=kind,
        )
    fields = copy.deepcopy(raw)
    for field in _LIST_FIELDS.intersection(fields):
        value = fields[field]
        if isinstance(value, str):
            fields[field] = [item.strip() for item in value.split(",") if item.strip()]
        elif not isinstance(value, list):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                f"{field} must be a list selected by the structured form.",
                path=f"{kind}.{field}",
            )

    if kind == "context" and (
        "budget_max_tokens" in fields or "budget_reserve_output_tokens" in fields
    ):
        budget = fields.get("budget")
        if budget is not None and not isinstance(budget, dict):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "Context budget must be an object.",
                path="contexts.budget",
            )
        budget = copy.deepcopy(budget or {})
        if "budget_max_tokens" in fields:
            budget["max_tokens"] = fields.pop("budget_max_tokens")
        if "budget_reserve_output_tokens" in fields:
            budget["reserve_output_tokens"] = fields.pop(
                "budget_reserve_output_tokens"
            )
        fields["budget"] = budget

    if kind == "identity" and (
        "framework" in fields or "framework_agent_key" in fields
    ):
        framework = fields.pop("framework", "contract_fixture")
        agent_key = fields.pop("framework_agent_key", None)
        if not isinstance(framework, str) or not isinstance(agent_key, str):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "Identity bindings need a framework and agent key.",
                path="agent_identities.framework_bindings",
            )
        fields["framework_bindings"] = [
            {"framework": framework, "agent_key": agent_key}
        ]

    if kind == "approval" and (
        {"revision_kind", "revision", "exact_revision"}.intersection(fields)
    ):
        binding = fields.get("revision_binding")
        if binding is not None and not isinstance(binding, dict):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "Approval revision binding must be an object.",
                path="approvals.revision_binding",
            )
        binding = copy.deepcopy(binding or {})
        if "revision_kind" in fields:
            binding["kind"] = fields.pop("revision_kind")
        if "revision" in fields:
            binding["revision"] = fields.pop("revision")
        if "exact_revision" in fields:
            binding["exact"] = fields.pop("exact_revision")
        fields["revision_binding"] = binding

    if kind == "evidence":
        if "producer_id" in fields or "producer_type" in fields:
            producer = fields.get("producer")
            if producer is not None and not isinstance(producer, dict):
                raise ContractWorkbenchError(
                    "WORKBENCH_VALUE_INVALID",
                    "Evidence producer must be an object.",
                    path="governance_evidence.records.producer",
                )
            producer = copy.deepcopy(producer or {})
            if "producer_id" in fields:
                producer["id"] = fields.pop("producer_id")
            if "producer_type" in fields:
                producer["type"] = fields.pop("producer_type")
            fields["producer"] = producer
        if "tool_name" in fields or "tool_version" in fields:
            tool = fields.get("tool")
            if tool is not None and not isinstance(tool, dict):
                raise ContractWorkbenchError(
                    "WORKBENCH_VALUE_INVALID",
                    "Evidence tool must be an object.",
                    path="governance_evidence.records.tool",
                )
            tool = copy.deepcopy(tool or {})
            if "tool_name" in fields:
                tool["name"] = fields.pop("tool_name")
            if "tool_version" in fields:
                tool["version"] = fields.pop("tool_version")
            fields["tool"] = tool

    if kind == "relation" and (
        {"source_kind", "source_ref", "target_kind", "target_ref"}.intersection(
            fields
        )
    ):
        source = fields.get("source")
        target = fields.get("target")
        if (source is not None and not isinstance(source, dict)) or (
            target is not None and not isinstance(target, dict)
        ):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "Relation endpoints must be structured objects.",
                path="agentic_network.relations",
            )
        source = copy.deepcopy(source or {})
        target = copy.deepcopy(target or {})
        if "source_kind" in fields:
            source["kind"] = fields.pop("source_kind")
        if "source_ref" in fields:
            source["ref"] = fields.pop("source_ref")
        if "target_kind" in fields:
            target["kind"] = fields.pop("target_kind")
        if "target_ref" in fields:
            target["ref"] = fields.pop("target_ref")
        fields["source"] = source
        fields["target"] = target

    if kind == "revocation" and (
        "target_kind" in fields or "target_ref" in fields
    ):
        target = fields.get("target")
        if target is not None and not isinstance(target, dict):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "Revocation target must be a structured object.",
                path="agentic_network.revocations.target",
            )
        target = copy.deepcopy(target or {})
        target_kind = fields.pop("target_kind", target.get("kind"))
        target_ref = fields.pop("target_ref", None)
        target["kind"] = target_kind
        reference_field = {
            "agent_identity": "identity_ref",
            "membership": "membership_ref",
            "protocol_target": "protocol_target_ref",
            "approval_record": "approval_record_ref",
            "delegation": "delegation_ref",
            "handoff": "handoff_ref",
        }.get(str(target_kind))
        if target_kind == "capability_assignment":
            target["principal_type"] = fields.pop(
                "principal_type", target.get("principal_type", "agent_identity")
            )
            if target_ref is not None:
                target["principal_ref"] = target_ref
            if "capability_ref" in fields:
                target["capability_ref"] = fields.pop("capability_ref")
        elif reference_field and target_ref is not None:
            target[reference_field] = target_ref
        fields["target"] = target
    return fields


def _structured_construct_value(value: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise ContractWorkbenchError(
            "WORKBENCH_VALUE_INVALID",
            "The construct form must provide a reference and fields.",
        )
    reference = value.get("reference")
    fields = value.get("fields", {})
    if not isinstance(reference, str) or not reference:
        raise ContractWorkbenchError(
            "WORKBENCH_VALUE_INVALID",
            "The construct reference must be a non-empty identifier.",
        )
    if not isinstance(fields, dict):
        raise ContractWorkbenchError(
            "WORKBENCH_VALUE_INVALID",
            "The construct form fields must be an object.",
        )
    return reference, fields


def _apply_mutation(document: dict[str, Any], mutation: ContractMutation) -> None:
    operation = mutation.operation
    if operation == "upsert_construct":
        kind = mutation.target
        collection, key = _construct_collection(document, kind)
        reference, raw_fields = _structured_construct_value(mutation.value)
        fields = _normalise_construct_fields(kind, raw_fields)
        existing = next(
            (
                item
                for item in collection
                if isinstance(item, dict) and item.get(key) == reference
            ),
            None,
        )
        if existing is None:
            collection.append({key: reference, **fields})
        else:
            if kind == "identity" and "framework_bindings" in fields:
                current_bindings = _map_items(existing.get("framework_bindings"))
                submitted_bindings = _map_items(fields.get("framework_bindings"))
                submitted_frameworks = {
                    item.get("framework") for item in submitted_bindings
                }
                fields["framework_bindings"] = submitted_bindings + [
                    item
                    for item in current_bindings
                    if item.get("framework") not in submitted_frameworks
                ]
            existing.update(fields)
        return

    if operation == "remove_construct":
        kind = mutation.target
        collection, key = _construct_collection(document, kind)
        if isinstance(mutation.value, str):
            reference = mutation.value
        elif isinstance(mutation.value, dict):
            reference = mutation.value.get("reference")
        else:
            reference = None
        if not isinstance(reference, str) or not reference:
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "The remove form must select a construct reference.",
                path=kind,
            )
        for index, item in enumerate(collection):
            if isinstance(item, dict) and item.get(key) == reference:
                del collection[index]
                return
        raise ContractWorkbenchError(
            "WORKBENCH_TARGET_UNKNOWN",
            f"No {kind} named {reference!r} exists in the contract.",
            path=f"{kind}.{reference}",
        )

    if operation == "toggle_context_resource":
        if not isinstance(mutation.value, dict):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "The resource form must provide a path, placement, and enabled state.",
            )
        path = mutation.value.get("path")
        placement = mutation.value.get("placement")
        enabled = mutation.value.get("enabled", True)
        if (
            not isinstance(path, str)
            or not path
            or placement not in {"include", "exclude", "authority"}
            or not isinstance(enabled, bool)
        ):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "Resource path, placement, and enabled state are required.",
                path=f"contexts.{mutation.target}",
            )
        context = _find(
            _map_items(document.get("contexts")),
            "name",
            mutation.target,
            kind="context",
        )
        values = context.setdefault(str(placement), [])
        if not isinstance(values, list):
            raise ContractWorkbenchError(
                "WORKBENCH_SHAPE_INVALID",
                f"Context {placement} is not a list.",
                path=f"contexts.{mutation.target}.{placement}",
            )
        _toggle(values, path, enabled)
        return

    if operation == "toggle_policy_rule":
        if not isinstance(mutation.value, dict):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "The policy rule form must provide an effect, rule, and enabled state.",
            )
        effect = mutation.value.get("effect")
        rule = mutation.value.get("rule")
        enabled = mutation.value.get("enabled", True)
        if (
            effect not in {"deny", "require"}
            or not isinstance(rule, str)
            or not rule
            or not isinstance(enabled, bool)
        ):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "Policy effect, rule, and enabled state are required.",
                path=f"policies.{mutation.target}",
            )
        policy = _find(
            _map_items(document.get("policies")),
            "name",
            mutation.target,
            kind="policy",
        )
        rules = policy.setdefault(str(effect), [])
        if not isinstance(rules, list):
            raise ContractWorkbenchError(
                "WORKBENCH_SHAPE_INVALID",
                f"Policy {effect} rules are not a list.",
                path=f"policies.{mutation.target}.{effect}",
            )
        _toggle(rules, rule, enabled)
        return

    if operation == "set_profile":
        if not isinstance(mutation.value, dict):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "The profile form must provide name, version, and status.",
                path="project.profile",
            )
        name = mutation.value.get("name")
        version = mutation.value.get("version")
        status = mutation.value.get("status")
        if not all(isinstance(item, str) and item for item in (name, version, status)):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "Profile name, version, and status must be non-empty strings.",
                path="project.profile",
            )
        project = document.get("project")
        if not isinstance(project, dict):
            raise ContractWorkbenchError(
                "WORKBENCH_TARGET_UNKNOWN",
                "The project block is missing.",
                path="project",
            )
        project["profile"] = name
        project["profile_pack"] = {
            "name": name,
            "version": version,
            "status": status,
        }
        return

    if operation == "refresh_lock":
        if mutation.target != "nornyx.agentic_network.lock" or mutation.value is not True:
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "The lock form must explicitly request a temporary lock refresh.",
                path="nornyx.agentic_network.lock",
            )
        return

    if operation == "set_project_purpose":
        if not isinstance(mutation.value, str):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "Project purpose must be a string.",
                path="project.purpose",
            )
        project = document.get("project")
        if not isinstance(project, dict):
            raise ContractWorkbenchError("WORKBENCH_TARGET_UNKNOWN", "The project block is missing.", path="project")
        project["purpose"] = mutation.value
        return

    if operation == "toggle_identity_capability":
        capability, enabled = _value_switch(mutation.value, noun="capability")
        declared = {str(item.get("name")) for item in _map_items(document.get("capabilities"))}
        if capability not in declared:
            raise ContractWorkbenchError(
                "WORKBENCH_CAPABILITY_UNKNOWN",
                f"Capability {capability!r} is not declared.",
                path=f"capabilities.{capability}",
            )
        identity = _find(
            _map_items(document.get("agent_identities")),
            "id",
            mutation.target,
            kind="identity",
        )
        identity_refs = identity.setdefault("capability_refs", [])
        if not isinstance(identity_refs, list):
            raise ContractWorkbenchError(
                "WORKBENCH_SHAPE_INVALID",
                "identity capability_refs is not a list.",
                path=f"agent_identities.{mutation.target}.capability_refs",
            )
        _toggle(identity_refs, capability, enabled)
        network = document.get("agentic_network", {})
        memberships = _map_items(network.get("memberships")) if isinstance(network, dict) else []
        for membership in memberships:
            if membership.get("identity_ref") != mutation.target:
                continue
            refs = membership.setdefault("capability_refs", [])
            if isinstance(refs, list):
                _toggle(refs, capability, enabled)
        return

    if operation == "set_zone_share_category":
        category, enabled = _value_switch(mutation.value, noun="category")
        network = document.get("agentic_network")
        if not isinstance(network, dict):
            raise ContractWorkbenchError("WORKBENCH_TARGET_UNKNOWN", "The agentic_network block is missing.")
        zone = _find(
            _map_items(network.get("trust_zones")),
            "id",
            mutation.target,
            kind="trust zone",
        )
        allowlist = zone.setdefault("share_allowlist", [])
        if not isinstance(allowlist, list):
            raise ContractWorkbenchError(
                "WORKBENCH_SHAPE_INVALID",
                "zone share_allowlist is not a list.",
                path=f"agentic_network.trust_zones.{mutation.target}.share_allowlist",
            )
        _toggle(allowlist, category, enabled)
        return

    if operation == "set_approval_expiry":
        if not isinstance(mutation.value, str):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "Approval expiry must be an RFC 3339 timestamp string.",
                path=f"approvals.{mutation.target}.expires_at",
            )
        approval = _find(
            _map_items(document.get("approvals")),
            "name",
            mutation.target,
            kind="approval",
        )
        approval["expires_at"] = mutation.value
        return

    if operation == "set_subject_revision":
        if not isinstance(mutation.value, str):
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "Subject revision must be a string.",
                path=mutation.target or "agentic_network.subject_revision",
            )
        target = mutation.target or "agentic_network.subject_revision"
        if target in {"agentic_network", "agentic_network.subject_revision"}:
            network = document.get("agentic_network")
            if not isinstance(network, dict):
                raise ContractWorkbenchError("WORKBENCH_TARGET_UNKNOWN", "The agentic_network block is missing.")
            network["subject_revision"] = mutation.value
            return
        if target in {"governance_evidence", "governance_evidence.subject_revision"}:
            evidence = document.get("governance_evidence")
            if not isinstance(evidence, dict):
                raise ContractWorkbenchError("WORKBENCH_TARGET_UNKNOWN", "The governance_evidence block is missing.")
            evidence["subject_revision"] = mutation.value
            return
        if target == "all":
            network = document.get("agentic_network")
            evidence = document.get("governance_evidence")
            if isinstance(network, dict):
                network["subject_revision"] = mutation.value
            if isinstance(evidence, dict):
                evidence["subject_revision"] = mutation.value
                for record in _map_items(evidence.get("records")):
                    record["subject_revision"] = mutation.value
            for approval in _map_items(document.get("approvals")):
                binding = approval.get("revision_binding")
                if isinstance(binding, dict):
                    binding["revision"] = mutation.value
            return
        raise ContractWorkbenchError(
            "WORKBENCH_TARGET_UNKNOWN",
            "Subject revision target must be agentic_network.subject_revision, governance_evidence.subject_revision, or all.",
            path=target,
        )

    if operation == "remove_evidence_field":
        if not isinstance(mutation.value, str) or not mutation.value:
            raise ContractWorkbenchError(
                "WORKBENCH_VALUE_INVALID",
                "The evidence field to remove must be a non-empty string.",
            )
        evidence = document.get("governance_evidence")
        if not isinstance(evidence, dict):
            raise ContractWorkbenchError("WORKBENCH_TARGET_UNKNOWN", "The governance_evidence block is missing.")
        record = _find(
            _map_items(evidence.get("records")),
            "id",
            mutation.target,
            kind="evidence record",
        )
        if mutation.value not in record:
            raise ContractWorkbenchError(
                "WORKBENCH_FIELD_UNKNOWN",
                f"Evidence record {mutation.target!r} has no field {mutation.value!r}.",
                path=f"governance_evidence.records.{mutation.target}.{mutation.value}",
            )
        del record[mutation.value]
        return

    raise ContractWorkbenchError(
        "WORKBENCH_OPERATION_UNSUPPORTED",
        f"Unsupported workbench operation: {operation}",
    )


def _dump_canonical(document: dict[str, Any]) -> str:
    return yaml.safe_dump(
        document,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=100,
    )


def validate_workbench(request: ContractWorkbenchRequest) -> ContractValidation:
    """Apply mutations in isolation, then reparse and validate real Nornyx.

    ``valid`` reports semantic parse/check/composition validity.  Lock drift is
    reported separately through ``lock_status`` and ``AN_LOCK_*`` diagnostics,
    because a meaningful source edit can be semantically valid while correctly
    making the old generated controls and lock stale.
    """

    committed_root = _contract_root(request.contract_id)
    with tempfile.TemporaryDirectory(prefix="nornyx-contract-workbench-") as temporary:
        root = Path(temporary) / request.contract_id
        shutil.copytree(committed_root, root)
        contract_path = root / "network.nyx"

        initial, _, _, parse_failure = _validate_document(contract_path)
        if initial is None:
            finding = parse_failure or _error_finding(
                "CONTRACT_PARSE_FAILED",
                "The committed contract could not be parsed.",
            )
            return ContractValidation(
                valid=False,
                source=contract_path.read_text(encoding="utf-8", errors="replace"),
                canonical_document=None,
                diagnostics=(finding,),
                lock_status=EvidenceStatus.UNKNOWN,
            )

        candidate = copy.deepcopy(initial)
        refresh_requested = any(
            mutation.operation == "refresh_lock" for mutation in request.mutations
        )
        try:
            for mutation in request.mutations:
                _apply_mutation(candidate, mutation)
        except ContractWorkbenchError as exc:
            nodes, edges = _graph(candidate)
            return ContractValidation(
                valid=False,
                source=_dump_canonical(candidate),
                canonical_document=candidate,
                nodes=nodes,
                edges=edges,
                diagnostics=(_error_finding(exc.code, str(exc), path=exc.path),),
                lock_status=EvidenceStatus.UNKNOWN,
            )

        source = _dump_canonical(candidate)
        contract_path.write_text(source, encoding="utf-8", newline="\n")
        document, composition, raw_diagnostics, parse_failure = _validate_document(contract_path)
        semantic_findings = tuple(_finding_from_diagnostic(item) for item in raw_diagnostics)
        if parse_failure is not None:
            semantic_findings += (parse_failure,)
        semantic_valid = document is not None and composition is not None and not any(
            getattr(item, "level", None) == "error" for item in raw_diagnostics
        )

        generated: tuple[dict[str, Any], ...] = ()
        lock_refreshed = False
        if semantic_valid and document is not None and composition is not None:
            try:
                rendered = render_agentic_network_artifacts(document, composition)
                generated = _decoded_controls(rendered)
                if refresh_requested:
                    _refresh_temporary_lock(root, document, composition, rendered)
                    lock_refreshed = True
            except Exception as exc:
                semantic_valid = False
                semantic_findings += (
                    _error_finding(
                        "CONTROL_RENDER_FAILED",
                        f"Nornyx could not render generated controls ({type(exc).__name__}).",
                        path="agentic_network",
                    ),
                )

        lock_status, lock_findings = _lock_findings(root, document, composition)
        graph_document = document if document is not None else candidate
        nodes, edges = _graph(graph_document, lock_status=lock_status)

        return ContractValidation(
            valid=semantic_valid,
            source=source,
            canonical_document=graph_document,
            nodes=nodes,
            edges=edges,
            diagnostics=semantic_findings + lock_findings,
            generated_controls=generated,
            lock_status=lock_status,
            lock_refreshed=lock_refreshed,
            semantic_paths_only=True,
        )


# Router-friendly aliases retained as a tiny compatibility surface.
explore_contract = get_contract
run_contract_workbench = validate_workbench
validate_contract_workbench = validate_workbench


__all__ = [
    "ContractWorkbenchError",
    "explore_contract",
    "get_contract",
    "list_contracts",
    "run_contract_workbench",
    "validate_contract_workbench",
    "validate_workbench",
]
