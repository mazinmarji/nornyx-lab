import { useEffect, useMemo, useState, type FormEvent } from "react";
import { academyApi } from "../api/client";
import { CausalFindings } from "../components/BuilderDiagnostics";
import { ContractGraph } from "../components/Diagrams";
import { ErrorNotice, InfoNotice } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useAsyncTask } from "../components/useAsyncTask";
import type {
  ContractConstructKind,
  ContractDetail,
  ContractMutation,
  ContractValidation,
} from "../types";

type BuilderKind =
  | "project"
  | "profile"
  | "resource"
  | "policy_rule"
  | "lock"
  | ContractConstructKind;
type BuilderAction = "create" | "update" | "remove";
type FormValue = string | boolean;
type FormValues = Record<string, FormValue>;

interface FieldDefinition {
  name: string;
  label: string;
  type: "text" | "textarea" | "list" | "number" | "boolean" | "select";
  help?: string;
  options?: readonly string[];
  optional?: boolean;
}

interface BuilderDefinition {
  kind: BuilderKind;
  label: string;
  help: string;
  key?: "name" | "id";
  fields: readonly FieldDefinition[];
  defaults: FormValues;
  special?: true;
}

const timestamps = {
  valid_from: "2026-01-01T00:00:00Z",
  expires_at: "2026-12-01T00:00:00Z",
};

const definitions: readonly BuilderDefinition[] = [
  { kind: "project", label: "Project", help: "Edit the project purpose without exposing a YAML path.", fields: [{ name: "purpose", label: "Purpose", type: "textarea" }], defaults: { purpose: "Govern a bounded agent network." }, special: true },
  { kind: "profile", label: "Governance profile", help: "Select the real profile pack resolved by Nornyx.", fields: [{ name: "name", label: "Profile", type: "select", options: ["agentic_network"] }, { name: "version", label: "Pack version", type: "text" }, { name: "status", label: "Pack status", type: "select", options: ["candidate", "stable", "deprecated"] }], defaults: { name: "agentic_network", version: "0.1.0", status: "candidate" }, special: true },
  { kind: "context", label: "Context", help: "Create or edit readable resources, authority sources, and token budget.", key: "name", fields: [{ name: "include", label: "Included resource patterns", type: "list", help: "Comma-separated local paths or glob patterns." }, { name: "exclude", label: "Excluded resource patterns", type: "list" }, { name: "authority", label: "Authority sources", type: "list" }, { name: "budget_max_tokens", label: "Maximum tokens", type: "number" }, { name: "budget_reserve_output_tokens", label: "Reserved output tokens", type: "number" }], defaults: { include: "README.md", exclude: ".env, secrets/**", authority: "network.nyx", budget_max_tokens: "32000", budget_reserve_output_tokens: "4000" } },
  { kind: "resource", label: "Context resource", help: "Place a local resource pattern in a context include, exclude, or authority list.", fields: [{ name: "context_ref", label: "Context", type: "text" }, { name: "path", label: "Local path or glob", type: "text" }, { name: "placement", label: "Boundary", type: "select", options: ["include", "exclude", "authority"] }, { name: "enabled", label: "Present in this boundary", type: "boolean" }], defaults: { context_ref: "", path: "README.md", placement: "include", enabled: true }, special: true },
  { kind: "agent", label: "Role-oriented agent", help: "Create or edit an agent role and its governing policy.", key: "name", fields: [{ name: "role", label: "Role", type: "textarea" }, { name: "policy", label: "Policy reference", type: "text" }], defaults: { role: "Perform a bounded task.", policy: "" } },
  { kind: "policy", label: "Policy", help: "Create or edit canonical deny and require rule lists.", key: "name", fields: [{ name: "deny", label: "Denied rules", type: "list" }, { name: "require", label: "Required rules", type: "list" }], defaults: { deny: "undeclared_capability_use", require: "exact_revision_binding" } },
  { kind: "policy_rule", label: "Policy rule", help: "Add or remove one named deny/require rule from a policy.", fields: [{ name: "policy_ref", label: "Policy", type: "text" }, { name: "effect", label: "Effect", type: "select", options: ["deny", "require"] }, { name: "rule", label: "Rule", type: "text" }, { name: "enabled", label: "Rule is present", type: "boolean" }], defaults: { policy_ref: "", effect: "deny", rule: "undeclared_capability_use", enabled: true }, special: true },
  { kind: "capability", label: "Capability", help: "Declare bounded actions, scope, risk, gates, approvals, and evidence.", key: "name", fields: [{ name: "actions", label: "Action classes", type: "list" }, { name: "risk", label: "Risk", type: "select", options: ["low", "medium", "high", "critical"] }, { name: "scope_type", label: "Scope type", type: "select", options: ["context"] }, { name: "scope_refs", label: "Context references", type: "list" }, { name: "delegable", label: "Delegable", type: "boolean" }, { name: "max_delegation_depth", label: "Maximum delegation depth", type: "number", optional: true }, { name: "required_gate_refs", label: "Required gates", type: "list" }, { name: "required_approval_refs", label: "Required approvals", type: "list" }, { name: "required_evidence_refs", label: "Required evidence", type: "list" }], defaults: { actions: "preview_action", risk: "low", scope_type: "context", scope_refs: "", delegable: false, max_delegation_depth: "", required_gate_refs: "", required_approval_refs: "", required_evidence_refs: "" } },
  { kind: "identity", label: "Agent identity", help: "Bind an agent role to non-human identity and capability declarations.", key: "id", fields: [{ name: "role_ref", label: "Agent role reference", type: "text" }, { name: "identity_class", label: "Identity class", type: "select", options: ["local_agent", "external_agent", "service_agent", "test_agent"] }, { name: "namespace", label: "Namespace", type: "text" }, { name: "subject", label: "Subject", type: "text" }, { name: "framework", label: "Framework binding", type: "text" }, { name: "framework_agent_key", label: "Framework agent key", type: "text" }, { name: "capability_refs", label: "Capability references", type: "list" }, { name: "status", label: "Status", type: "select", options: ["active", "suspended", "revoked", "expired"] }, { name: "valid_from", label: "Valid from", type: "text" }, { name: "expires_at", label: "Expires at", type: "text" }, { name: "revocation_refs", label: "Revocation references", type: "list" }, { name: "authority", label: "Authority", type: "select", options: ["non_human"] }, { name: "can_approve", label: "Can approve", type: "boolean", help: "The agentic-network profile requires false." }], defaults: { role_ref: "", identity_class: "local_agent", namespace: "academy.builder", subject: "new_agent", framework: "contract_fixture", framework_agent_key: "new_agent", capability_refs: "", status: "active", ...timestamps, revocation_refs: "", authority: "non_human", can_approve: false } },
  { kind: "approval", label: "Approval requirement", help: "Edit accountable human roles, revision binding, evidence, and expiry.", key: "name", fields: [{ name: "required_roles", label: "Required human roles", type: "list" }, { name: "eligible_roles", label: "Eligible human roles", type: "list" }, { name: "denied_actor_types", label: "Denied actor types", type: "list" }, { name: "required_evidence", label: "Required evidence", type: "list" }, { name: "required_for", label: "Required action classes", type: "list" }, { name: "timing", label: "Timing", type: "select", options: ["before_action"] }, { name: "accountable_authority", label: "Accountable authority", type: "text" }, { name: "revision_kind", label: "Revision kind", type: "select", options: ["git"] }, { name: "revision", label: "Exact subject revision", type: "text" }, { name: "exact_revision", label: "Exact revision required", type: "boolean" }, { name: "invalidation_conditions", label: "Invalidation conditions", type: "list" }, { name: "expires_at", label: "Expires at", type: "text" }], defaults: { required_roles: "network_governance_owner", eligible_roles: "network_governance_owner, security_reviewer", denied_actor_types: "ai_tool, autonomous_agent, model", required_evidence: "", required_for: "preview_action", timing: "before_action", accountable_authority: "network_governance_owner", revision_kind: "git", revision: `git:${"0".repeat(40)}`, exact_revision: true, invalidation_conditions: "revision_change", expires_at: "2026-12-01T00:00:00Z" } },
  { kind: "evidence", label: "Evidence record", help: "Create or edit typed, hashed evidence metadata; truth is not inferred.", key: "id", fields: [{ name: "type", label: "Evidence type", type: "text" }, { name: "schema_id", label: "Schema ID", type: "text" }, { name: "producer_id", label: "Producer ID", type: "text" }, { name: "producer_type", label: "Producer type", type: "select", options: ["human", "tool", "system", "external_service"] }, { name: "artifact", label: "Local artifact path", type: "text" }, { name: "content_hash", label: "SHA-256 content hash", type: "text" }, { name: "subject_revision", label: "Subject revision", type: "text" }, { name: "tool_name", label: "Producing tool", type: "text" }, { name: "tool_version", label: "Tool version", type: "text" }, { name: "generated_at", label: "Generated at", type: "text" }, { name: "expires_at", label: "Expires at", type: "text", optional: true }, { name: "status", label: "Observed status", type: "select", options: ["pass", "fail", "inconclusive", "observed"] }, { name: "dependencies", label: "Evidence dependencies", type: "list" }], defaults: { type: "builder_review", schema_id: "nornyx.example_evidence.v1", producer_id: "human.security_reviewer", producer_type: "human", artifact: "governance_evidence/builder_review.json", content_hash: `sha256:${"0".repeat(64)}`, subject_revision: `git:${"0".repeat(40)}`, tool_name: "local_record", tool_version: "1.0.0", generated_at: "2026-01-01T00:00:00Z", expires_at: "2026-12-01T00:00:00Z", status: "observed", dependencies: "" } },
  { kind: "trust_zone", label: "Trust zone", help: "Create or edit transition, sharing, and gate boundaries.", key: "id", fields: [{ name: "classification", label: "Classification", type: "select", options: ["governed_local", "internal", "isolated", "test", "external", "external_contract_only", "contract_only"] }, { name: "allowed_transition_targets", label: "Allowed transition targets", type: "list" }, { name: "share_allowlist", label: "Share allowlist", type: "list" }, { name: "never_share", label: "Never share", type: "list" }, { name: "ingress_gate_refs", label: "Ingress gates", type: "list" }, { name: "egress_gate_refs", label: "Egress gates", type: "list" }], defaults: { classification: "test", allowed_transition_targets: "", share_allowlist: "evidence_digest", never_share: "secrets, credentials, tokens, private_memory", ingress_gate_refs: "", egress_gate_refs: "" } },
  { kind: "membership", label: "Zone membership", help: "Assign an identity and bounded capabilities to a trust zone.", key: "id", fields: [{ name: "identity_ref", label: "Identity reference", type: "text" }, { name: "trust_zone_ref", label: "Trust zone reference", type: "text" }, { name: "capability_refs", label: "Capability references", type: "list" }, { name: "status", label: "Status", type: "select", options: ["authorized", "suspended", "revoked", "expired"] }, { name: "valid_from", label: "Valid from", type: "text" }, { name: "expires_at", label: "Expires at", type: "text" }, { name: "revocation_refs", label: "Revocation references", type: "list" }], defaults: { identity_ref: "", trust_zone_ref: "", capability_refs: "", status: "authorized", ...timestamps, revocation_refs: "" } },
  { kind: "protocol_target", label: "Protocol target", help: "Describe a contract-only MCP or A2A boundary; no endpoint or credential is accepted.", key: "id", fields: [{ name: "protocol", label: "Protocol", type: "select", options: ["mcp", "a2a"] }, { name: "version", label: "Declared version label", type: "text" }, { name: "execution_mode", label: "Execution mode", type: "select", options: ["contract_only"] }, { name: "live_connector_execution", label: "Live connector execution", type: "boolean" }, { name: "identity_refs", label: "Identity references", type: "list" }, { name: "source_membership_refs", label: "Source memberships", type: "list" }, { name: "source_zone_ref", label: "Source zone", type: "text" }, { name: "capability_refs", label: "Capability references", type: "list" }, { name: "trust_zone_ref", label: "Target trust zone", type: "text" }, { name: "share", label: "Share categories", type: "list" }, { name: "never_share", label: "Never share", type: "list" }, { name: "required_gate_refs", label: "Required gates", type: "list" }, { name: "required_approval_refs", label: "Required approvals", type: "list" }, { name: "required_evidence_refs", label: "Required evidence", type: "list" }], defaults: { protocol: "a2a", version: "declared-by-project", execution_mode: "contract_only", live_connector_execution: false, identity_refs: "", source_membership_refs: "", source_zone_ref: "", capability_refs: "", trust_zone_ref: "", share: "evidence_digest", never_share: "secrets, credentials, tokens, private_memory", required_gate_refs: "", required_approval_refs: "", required_evidence_refs: "" } },
  { kind: "gate", label: "Network gate", help: "Bind action classes and zone crossings to policies, approvals, and evidence.", key: "id", fields: [{ name: "action_classes", label: "Action classes", type: "list" }, { name: "source_zone_refs", label: "Source zones", type: "list" }, { name: "target_zone_refs", label: "Target zones", type: "list" }, { name: "required_policy_refs", label: "Required policies", type: "list" }, { name: "required_approval_refs", label: "Required approvals", type: "list" }, { name: "required_evidence_refs", label: "Required evidence", type: "list" }], defaults: { action_classes: "preview_action", source_zone_refs: "", target_zone_refs: "", required_policy_refs: "", required_approval_refs: "", required_evidence_refs: "" } },
  { kind: "revocation", label: "Revocation", help: "Declare a typed target, effective time, reason, approval, and evidence.", key: "id", fields: [{ name: "target_kind", label: "Target kind", type: "select", options: ["agent_identity", "membership", "capability_assignment", "protocol_target", "approval_record", "delegation", "handoff"] }, { name: "target_ref", label: "Target reference", type: "text" }, { name: "principal_type", label: "Capability principal type", type: "select", options: ["agent_identity", "membership"], optional: true }, { name: "capability_ref", label: "Capability reference", type: "text", optional: true }, { name: "effective_at", label: "Effective at", type: "text" }, { name: "reason", label: "Reason", type: "textarea" }, { name: "required_approval_refs", label: "Required approvals", type: "list" }, { name: "required_evidence_refs", label: "Required evidence", type: "list" }], defaults: { target_kind: "agent_identity", target_ref: "", principal_type: "agent_identity", capability_ref: "", effective_at: "2026-06-01T00:00:00Z", reason: "Revoke authority after a reviewed change.", required_approval_refs: "", required_evidence_refs: "" } },
  { kind: "delegation", label: "Delegation", help: "Lend one delegable capability within time, scope, zone, depth, and evidence bounds.", key: "id", fields: [{ name: "delegator_ref", label: "Delegator identity", type: "text" }, { name: "delegate_ref", label: "Delegate identity", type: "text" }, { name: "capability_ref", label: "Capability", type: "text" }, { name: "purpose", label: "Purpose", type: "textarea" }, { name: "actions", label: "Allowed actions", type: "list" }, { name: "scope_refs", label: "Scope references", type: "list" }, { name: "status", label: "Status", type: "select", options: ["active", "suspended", "revoked", "expired"] }, { name: "valid_from", label: "Valid from", type: "text" }, { name: "expires_at", label: "Expires at", type: "text" }, { name: "max_depth", label: "Maximum depth", type: "number" }, { name: "current_depth", label: "Current depth", type: "number" }, { name: "onward_delegation", label: "Onward delegation", type: "select", options: ["denied", "allowed_with_policy"] }, { name: "source_zone_ref", label: "Source zone", type: "text" }, { name: "target_zone_ref", label: "Target zone", type: "text" }, { name: "required_gate_refs", label: "Required gates", type: "list" }, { name: "required_policy_refs", label: "Required policies", type: "list" }, { name: "required_approval_refs", label: "Required approvals", type: "list" }, { name: "required_evidence_refs", label: "Required evidence", type: "list" }, { name: "revocation_refs", label: "Revocation references", type: "list" }], defaults: { delegator_ref: "", delegate_ref: "", capability_ref: "", purpose: "Delegate a bounded capability.", actions: "", scope_refs: "", status: "active", ...timestamps, max_depth: "1", current_depth: "0", onward_delegation: "denied", source_zone_ref: "", target_zone_ref: "", required_gate_refs: "", required_policy_refs: "", required_approval_refs: "", required_evidence_refs: "", revocation_refs: "" } },
  { kind: "handoff", label: "Responsibility handoff", help: "Transfer mission responsibility with explicit context and governance bounds.", key: "id", fields: [{ name: "from_identity_ref", label: "From identity", type: "text" }, { name: "to_identity_ref", label: "To identity", type: "text" }, { name: "purpose", label: "Purpose", type: "textarea" }, { name: "mission_ref", label: "Mission reference", type: "text" }, { name: "from_zone_ref", label: "From zone", type: "text" }, { name: "to_zone_ref", label: "To zone", type: "text" }, { name: "required_capability_refs", label: "Required capabilities", type: "list" }, { name: "delegation_refs", label: "Delegation references", type: "list" }, { name: "shared_context", label: "Shared context categories", type: "list" }, { name: "never_share", label: "Never share", type: "list" }, { name: "status", label: "Status", type: "select", options: ["initiated", "accepted", "completed", "rejected", "expired", "revoked", "superseded"] }, { name: "valid_from", label: "Valid from", type: "text" }, { name: "expires_at", label: "Expires at", type: "text" }, { name: "required_gate_refs", label: "Required gates", type: "list" }, { name: "required_approval_refs", label: "Required approvals", type: "list" }, { name: "required_evidence_refs", label: "Required evidence", type: "list" }, { name: "revocation_refs", label: "Revocation references", type: "list" }], defaults: { from_identity_ref: "", to_identity_ref: "", purpose: "Transfer bounded mission responsibility.", mission_ref: "", from_zone_ref: "", to_zone_ref: "", required_capability_refs: "", delegation_refs: "", shared_context: "evidence_digest", never_share: "secrets, credentials, tokens, private_memory", status: "initiated", ...timestamps, required_gate_refs: "", required_approval_refs: "", required_evidence_refs: "", revocation_refs: "" } },
  { kind: "relation", label: "Typed relation", help: "Connect canonical identities, capabilities, zones, approvals, delegations, or handoffs.", key: "id", fields: [{ name: "type", label: "Relation", type: "select", options: ["identifies", "owns", "advertises_capability", "delegates_to", "hands_off_to", "communicates_with", "crosses_trust_zone", "shares_with", "requires_approval_from", "revokes", "observed_by"] }, { name: "source_kind", label: "Source kind", type: "select", options: ["agent_identity", "capability", "trust_zone", "membership", "protocol_target", "delegation", "handoff", "approval", "revocation", "human_role"] }, { name: "source_ref", label: "Source reference", type: "text" }, { name: "target_kind", label: "Target kind", type: "select", options: ["agent_identity", "capability", "trust_zone", "membership", "protocol_target", "delegation", "handoff", "approval", "revocation", "human_role"] }, { name: "target_ref", label: "Target reference", type: "text" }, { name: "delegation_ref", label: "Delegation reference", type: "text", optional: true }, { name: "handoff_ref", label: "Handoff reference", type: "text", optional: true }, { name: "protocol_target_ref", label: "Protocol target reference", type: "text", optional: true }, { name: "share_categories", label: "Share categories", type: "list", optional: true }, { name: "description", label: "Description", type: "textarea", optional: true }], defaults: { type: "communicates_with", source_kind: "agent_identity", source_ref: "", target_kind: "agent_identity", target_ref: "", delegation_ref: "", handoff_ref: "", protocol_target_ref: "", share_categories: "", description: "" } },
  { kind: "lock", label: "Generated lock", help: "Regenerate controls and the lock only inside the temporary workbench copy.", fields: [{ name: "refresh", label: "Refresh copied controls and lock", type: "boolean" }], defaults: { refresh: true }, special: true },
];

const locations: Record<ContractConstructKind, { path: readonly string[]; key: "name" | "id" }> = {
  context: { path: ["contexts"], key: "name" },
  agent: { path: ["agents"], key: "name" },
  policy: { path: ["policies"], key: "name" },
  capability: { path: ["capabilities"], key: "name" },
  identity: { path: ["agent_identities"], key: "id" },
  approval: { path: ["approvals"], key: "name" },
  evidence: { path: ["governance_evidence", "records"], key: "id" },
  trust_zone: { path: ["agentic_network", "trust_zones"], key: "id" },
  membership: { path: ["agentic_network", "memberships"], key: "id" },
  protocol_target: { path: ["agentic_network", "protocol_targets"], key: "id" },
  gate: { path: ["agentic_network", "network_gates"], key: "id" },
  revocation: { path: ["agentic_network", "revocations"], key: "id" },
  delegation: { path: ["agentic_network", "delegations"], key: "id" },
  handoff: { path: ["agentic_network", "handoffs"], key: "id" },
  relation: { path: ["agentic_network", "relations"], key: "id" },
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function valueAt(document: Record<string, unknown>, path: readonly string[]): unknown {
  let current: unknown = document;
  for (const part of path) current = asRecord(current)?.[part];
  return current;
}

function recordsFor(detail: ContractDetail | null, kind: ContractConstructKind): Record<string, unknown>[] {
  if (!detail) return [];
  const value = valueAt(detail.canonical_document, locations[kind].path);
  return Array.isArray(value) ? value.map(asRecord).filter((item): item is Record<string, unknown> => item !== null) : [];
}

function toFormValue(value: unknown): FormValue {
  if (typeof value === "boolean") return value;
  if (Array.isArray(value)) return value.map(String).join(", ");
  return value === null || value === undefined ? "" : String(value);
}

function flattenRecord(kind: ContractConstructKind, record: Record<string, unknown>, fields: readonly FieldDefinition[]): FormValues {
  const flattened: Record<string, unknown> = { ...record };
  if (kind === "context") {
    const budget = asRecord(record.budget);
    flattened.budget_max_tokens = budget?.max_tokens;
    flattened.budget_reserve_output_tokens = budget?.reserve_output_tokens;
  }
  if (kind === "identity") {
    const binding = Array.isArray(record.framework_bindings) ? asRecord(record.framework_bindings[0]) : null;
    flattened.framework = binding?.framework;
    flattened.framework_agent_key = binding?.agent_key;
  }
  if (kind === "approval") {
    const binding = asRecord(record.revision_binding);
    flattened.revision_kind = binding?.kind;
    flattened.revision = binding?.revision;
    flattened.exact_revision = binding?.exact;
  }
  if (kind === "evidence") {
    const producer = asRecord(record.producer);
    const tool = asRecord(record.tool);
    flattened.producer_id = producer?.id;
    flattened.producer_type = producer?.type;
    flattened.tool_name = tool?.name;
    flattened.tool_version = tool?.version;
  }
  if (kind === "relation") {
    const source = asRecord(record.source);
    const target = asRecord(record.target);
    flattened.source_kind = source?.kind;
    flattened.source_ref = source?.ref;
    flattened.target_kind = target?.kind;
    flattened.target_ref = target?.ref;
  }
  if (kind === "revocation") {
    const target = asRecord(record.target);
    flattened.target_kind = target?.kind;
    flattened.target_ref = Object.entries(target ?? {}).find(([key]) => key.endsWith("_ref"))?.[1];
    flattened.principal_type = target?.principal_type;
    flattened.capability_ref = target?.capability_ref;
  }
  return Object.fromEntries(fields.map((field) => [field.name, toFormValue(flattened[field.name])]));
}

function firstReference(detail: ContractDetail | null, kind: ContractConstructKind): string {
  const record = recordsFor(detail, kind)[0];
  return String(record?.[locations[kind].key] ?? "");
}

function defaultValues(definition: BuilderDefinition, detail: ContractDetail | null): FormValues {
  const values = { ...definition.defaults };
  const document = detail?.canonical_document;
  const project = asRecord(document?.project);
  const network = asRecord(document?.agentic_network);
  const revision = String(network?.subject_revision ?? `git:${"0".repeat(40)}`);
  const identity = firstReference(detail, "identity");
  const identities = recordsFor(detail, "identity");
  const secondIdentity = String(identities[1]?.id ?? identity);
  const zone = firstReference(detail, "trust_zone");
  const capability = firstReference(detail, "capability");
  const context = firstReference(detail, "context");
  const policy = firstReference(detail, "policy");
  const approval = firstReference(detail, "approval");
  const evidence = firstReference(detail, "evidence");
  const gate = firstReference(detail, "gate");
  const membership = firstReference(detail, "membership");
  const goals = document?.goals;
  const goal = Array.isArray(goals) ? String(asRecord(goals[0])?.id ?? "MISSION-001") : "MISSION-001";
  if (definition.kind === "project") values.purpose = String(project?.purpose ?? values.purpose);
  if (definition.kind === "profile") {
    const pack = asRecord(project?.profile_pack);
    values.name = String(project?.profile ?? values.name);
    values.version = String(pack?.version ?? values.version);
    values.status = String(pack?.status ?? values.status);
  }
  if (definition.kind === "resource") values.context_ref = context;
  if (definition.kind === "agent") values.policy = policy;
  if (definition.kind === "policy_rule") values.policy_ref = policy;
  if (definition.kind === "capability") values.scope_refs = context;
  if (definition.kind === "identity") {
    values.role_ref = firstReference(detail, "agent");
    values.capability_refs = capability;
  }
  if (definition.kind === "approval") {
    values.revision = revision;
    values.required_evidence = evidence;
  }
  if (definition.kind === "evidence") values.subject_revision = revision;
  if (definition.kind === "membership") {
    values.identity_ref = identity;
    values.trust_zone_ref = zone;
    values.capability_refs = capability;
  }
  if (definition.kind === "protocol_target") {
    values.identity_refs = identity;
    values.source_membership_refs = membership;
    values.source_zone_ref = zone;
    values.trust_zone_ref = zone;
    values.capability_refs = capability;
    values.required_gate_refs = gate;
    values.required_approval_refs = approval;
    values.required_evidence_refs = evidence;
  }
  if (definition.kind === "gate") {
    values.source_zone_refs = zone;
    values.target_zone_refs = zone;
    values.required_policy_refs = policy;
    values.required_evidence_refs = evidence;
  }
  if (definition.kind === "revocation") {
    values.target_ref = identity;
    values.required_approval_refs = approval;
    values.required_evidence_refs = evidence;
  }
  if (definition.kind === "delegation") {
    values.delegator_ref = identity;
    values.delegate_ref = secondIdentity;
    values.capability_ref = capability;
    values.actions = capability;
    values.scope_refs = context;
    values.source_zone_ref = zone;
    values.target_zone_ref = zone;
    values.required_gate_refs = gate;
    values.required_policy_refs = policy;
    values.required_evidence_refs = evidence;
  }
  if (definition.kind === "handoff") {
    values.from_identity_ref = identity;
    values.to_identity_ref = secondIdentity;
    values.mission_ref = goal;
    values.from_zone_ref = zone;
    values.to_zone_ref = zone;
    values.required_capability_refs = capability;
    values.required_gate_refs = gate;
    values.required_approval_refs = approval;
    values.required_evidence_refs = evidence;
  }
  if (definition.kind === "relation") {
    values.source_ref = identity;
    values.target_ref = secondIdentity;
  }
  return values;
}

function mutationSummary(mutation: ContractMutation): string {
  const value = asRecord(mutation.value);
  const reference = value?.reference;
  if (typeof reference === "string") return `${mutation.target}: ${reference}`;
  if (mutation.operation === "refresh_lock") return "temporary copy only";
  return mutation.target;
}

export function BuilderPage() {
  const baseline = useAsyncTask<ContractDetail>();
  const validation = useAsyncTask<ContractValidation>();
  const [contractId, setContractId] = useState<"atlas" | "ledger">("atlas");
  const [builderKind, setBuilderKind] = useState<BuilderKind>("project");
  const [action, setAction] = useState<BuilderAction>("update");
  const [reference, setReference] = useState("");
  const [values, setValues] = useState<FormValues>({ purpose: "Govern a bounded agent network." });
  const [mutations, setMutations] = useState<ContractMutation[]>([]);
  const definition = definitions.find((item) => item.kind === builderKind) ?? definitions[0];
  const constructKind = definition.key ? definition.kind as ContractConstructKind : null;
  const records = useMemo(() => constructKind ? recordsFor(baseline.data, constructKind) : [], [baseline.data, constructKind]);

  useEffect(() => {
    validation.clear();
    setMutations([]);
    void baseline.run(() => academyApi.contract(contractId));
  }, [contractId]); // stable async task methods

  useEffect(() => {
    const defaults = defaultValues(definition, baseline.data);
    if (!constructKind || action === "create") {
      setReference(action === "create" && constructKind ? `${constructKind}.new` : "");
      setValues(defaults);
      return;
    }
    const key = locations[constructKind].key;
    const record = records[0];
    setReference(String(record?.[key] ?? ""));
    setValues(record ? flattenRecord(constructKind, record, definition.fields) : defaults);
  }, [action, baseline.data, builderKind]);

  function selectReference(next: string) {
    setReference(next);
    if (!constructKind) return;
    const key = locations[constructKind].key;
    const record = records.find((item) => item[key] === next);
    if (record) setValues(flattenRecord(constructKind, record, definition.fields));
  }

  function fieldPayload(): Record<string, unknown> {
    const payload: Record<string, unknown> = {};
    for (const field of definition.fields) {
      const raw = values[field.name];
      if (field.optional && (raw === "" || raw === undefined)) continue;
      if (field.type === "list") payload[field.name] = String(raw ?? "").split(",").map((item) => item.trim()).filter(Boolean);
      else if (field.type === "number") payload[field.name] = Number(raw);
      else payload[field.name] = raw;
    }
    return payload;
  }

  function queueMutation(event: FormEvent) {
    event.preventDefault();
    let mutation: ContractMutation;
    const payload = fieldPayload();
    if (builderKind === "project") mutation = { operation: "set_project_purpose", target: "project.purpose", value: payload.purpose };
    else if (builderKind === "profile") mutation = { operation: "set_profile", target: "project.profile", value: payload };
    else if (builderKind === "resource") mutation = { operation: "toggle_context_resource", target: String(payload.context_ref), value: { path: payload.path, placement: payload.placement, enabled: payload.enabled } };
    else if (builderKind === "policy_rule") mutation = { operation: "toggle_policy_rule", target: String(payload.policy_ref), value: { effect: payload.effect, rule: payload.rule, enabled: payload.enabled } };
    else if (builderKind === "lock") mutation = { operation: "refresh_lock", target: "nornyx.agentic_network.lock", value: payload.refresh };
    else if (action === "remove") mutation = { operation: "remove_construct", target: builderKind, value: { reference } };
    else mutation = { operation: "upsert_construct", target: builderKind, value: { reference, fields: payload } };
    validation.clear();
    setMutations((current) => [...current, mutation]);
  }

  async function validate() {
    await validation.run(() => academyApi.validateWorkbench(contractId, mutations));
  }

  const previewNodes = validation.data?.nodes ?? baseline.data?.nodes ?? [];
  const previewEdges = validation.data?.edges ?? baseline.data?.edges ?? [];
  const allowAction = Boolean(constructKind);

  return (
    <div className="page">
      <header className="page-header tool-header"><div><p className="eyebrow">Schema-guided contract authoring</p><h1>Visual contract builder</h1><p>Create, edit, and remove canonical Nornyx constructs through labeled fields, then validate a temporary copy with the real parser, profile, generator, and lock verifier.</p></div></header>
      <InfoNotice title="Canonical .nyx stays authoritative"><p>The form maps to existing <code>.nyx</code> blocks—never a visual-only format. Context paths are the contract’s resource model; lock refreshes affect only the isolated workbench copy.</p></InfoNotice>
      <section className="builder-layout">
        <div className="builder-controls">
          <label><span>Base contract</span><select value={contractId} onChange={(event) => setContractId(event.target.value as "atlas" | "ledger")}><option value="atlas">Atlas</option><option value="ledger">Ledger</option></select></label>
          <form onSubmit={queueMutation} className="mutation-form">
            <h2>Add a structured change</h2>
            <label><span>Construct</span><select value={builderKind} onChange={(event) => setBuilderKind(event.target.value as BuilderKind)}>{definitions.map((item) => <option value={item.kind} key={item.kind}>{item.label}</option>)}</select><small>{definition.help}</small></label>
            {allowAction ? <label><span>Action</span><select value={action} onChange={(event) => setAction(event.target.value as BuilderAction)}><option value="update">Edit selected</option><option value="create">Create new</option><option value="remove">Remove selected</option></select></label> : null}
            {constructKind ? action === "create" ? <label><span>New {definition.key === "id" ? "ID" : "name"}</span><input value={reference} onChange={(event) => setReference(event.target.value)} required /></label> : <label><span>{definition.key === "id" ? "ID" : "Name"}</span><select value={reference} onChange={(event) => selectReference(event.target.value)} required>{records.map((record) => { const item = String(record[locations[constructKind].key]); return <option value={item} key={item}>{item}</option>; })}</select></label> : null}
            {action !== "remove" || !constructKind ? <div className="builder-field-list">{definition.fields.map((field) => {
              const value = values[field.name] ?? (field.type === "boolean" ? false : "");
              if (field.type === "boolean") return <label className="checkbox-row" key={field.name}><input type="checkbox" checked={Boolean(value)} onChange={(event) => setValues((current) => ({ ...current, [field.name]: event.target.checked }))} /><span>{field.label}</span>{field.help ? <small>{field.help}</small> : null}</label>;
              if (field.type === "textarea") return <label key={field.name}><span>{field.label}</span><textarea value={String(value)} onChange={(event) => setValues((current) => ({ ...current, [field.name]: event.target.value }))} required={!field.optional} />{field.help ? <small>{field.help}</small> : null}</label>;
              if (field.type === "select") return <label key={field.name}><span>{field.label}</span><select value={String(value)} onChange={(event) => setValues((current) => ({ ...current, [field.name]: event.target.value }))}>{field.options?.map((option) => <option key={option} value={option}>{option.replaceAll("_", " ")}</option>)}</select>{field.help ? <small>{field.help}</small> : null}</label>;
              return <label key={field.name}><span>{field.label}</span><input type={field.type === "number" ? "number" : "text"} value={String(value)} onChange={(event) => setValues((current) => ({ ...current, [field.name]: event.target.value }))} required={field.type !== "list" && !field.optional} />{field.help ? <small>{field.help}</small> : null}</label>;
            })}</div> : null}
            <button className="button button-secondary" type="submit">Queue structured change</button>
          </form>
          <section className="mutation-queue"><div className="section-heading compact-heading"><div><p className="eyebrow">Working changes</p><h2>Mutation queue</h2></div><button type="button" className="text-button" onClick={() => { setMutations([]); validation.clear(); }}>Clear</button></div>{mutations.length ? <ol>{mutations.map((mutation, index) => <li key={`${mutation.operation}-${index}`}><div><strong>{mutation.operation.replaceAll("_", " ")}</strong><span>{mutationSummary(mutation)}</span></div><button type="button" className="text-button" onClick={() => { validation.clear(); setMutations((current) => current.filter((_, itemIndex) => itemIndex !== index)); }}>Remove</button></li>)}</ol> : <p className="muted">No changes yet. Validating checks the untouched base contract.</p>}<button className="button button-primary" type="button" disabled={validation.loading} onClick={() => void validate()}>{validation.loading ? "Validating with Nornyx…" : "Apply and validate"}</button></section>
        </div>
        <div className="builder-preview">
          <div className="section-heading"><div><p className="eyebrow">{validation.data ? "Validated mutation graph" : "Authoritative baseline graph"}</p><h2>{baseline.data?.summary.name ?? "Contract preview"}</h2></div>{validation.data ? <StatusBadge status={validation.data.valid ? "pass" : "fail"} /> : null}</div>
          {previewNodes.length ? <ContractGraph nodes={previewNodes} edges={previewEdges} /> : null}
          {baseline.error ? <ErrorNotice message={baseline.error} /> : null}
          {validation.error ? <ErrorNotice title="Workbench validation failed" message={validation.error} /> : null}
          {validation.data ? <section className="validation-result"><h3>{validation.data.valid ? "Contract is valid" : "Contract needs repair"}</h3><p>Lock status: <StatusBadge status={validation.data.lock_status} />{validation.data.lock_refreshed ? " Refreshed inside the temporary copy." : " Compared with the committed lock."}</p>{validation.data.diagnostics.length ? <CausalFindings findings={validation.data.diagnostics} /> : <p>No diagnostics were returned.</p>}<details open><summary>Authoritative returned source</summary><pre className="source-view"><code>{validation.data.source}</code></pre></details><details><summary>Generated controls ({validation.data.generated_controls.length})</summary><pre><code>{JSON.stringify(validation.data.generated_controls, null, 2)}</code></pre></details><p className="limitation">{validation.data.semantic_paths_only ? "Forms map to semantic fields; comments and original YAML formatting are not promised to round-trip." : "The response reports additional mutation semantics."}</p></section> : <p className="preview-placeholder">Queue a structured change and validate to synchronize the graph, canonical source, diagnostics, generated controls, and lock status.</p>}
        </div>
      </section>
    </div>
  );
}
