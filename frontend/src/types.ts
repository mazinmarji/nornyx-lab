export type LoadState = "idle" | "loading" | "success" | "error";

export type ModuleStatus =
  | "not_started"
  | "in_progress"
  | "needs_review"
  | "complete";

export type EvidenceStatus = "pass" | "fail" | "missing" | "unknown";
export type ClaimStatus = "supported" | "unsupported" | "indeterminate";
export type CounterMeaning =
  | "prevented_before_execution"
  | "attempted_not_completed"
  | "executed"
  | "not_planned"
  | "indeterminate";

export interface Health {
  status: "ok";
  api_version: string;
}

export interface PlatformInfo {
  api_version: string;
  academy_version: string;
  nornyx_runtime_version: string;
  nornyx_audited_main_commit: string;
  nornyx_main_delta: string;
  adapter_version: string;
  spi_version: string;
  deterministic_offline: boolean;
  default_actions_are_inert: boolean;
  assurance_tier_ceiling: string;
}

export interface ConceptRef {
  id: string;
  name: string;
  summary: string;
}

export interface CompletionRule {
  requires_execution: boolean;
  assessment_id: string;
  minimum_score: number;
  required_challenges: string[];
}

export interface CurriculumModule {
  id: string;
  legacy_lab_id: string | null;
  kind: "foundation" | "lab" | "capstone";
  title: string;
  eyebrow: string;
  summary: string;
  why_it_matters: string;
  difficulty: "beginner" | "intermediate" | "advanced";
  minutes: number;
  prerequisites: string[];
  concepts: string[];
  outcomes: string[];
  interaction: string;
  scenario_id: string | null;
  completion: CompletionRule;
  migration_classification: string | null;
  status: ModuleStatus;
  score: number | null;
}

export interface LearningPath {
  id: string;
  title: string;
  audience: string;
  summary: string;
  prerequisites: string[];
  estimated_minutes: number;
  concepts: string[];
  module_ids: string[];
  outcomes: string[];
  completion_criteria: string;
  completed_modules: number;
  total_modules: number;
}

export interface CurriculumCatalog {
  version: string;
  modules: CurriculumModule[];
  paths: LearningPath[];
  concepts: ConceptRef[];
}

export interface PlannerInput {
  task: string;
  context: string;
  context_origin: string;
  context_authority: "decides" | "informs_only";
  context_taint: "trusted" | "untrusted" | "mixed";
  planner_kind: "deterministic_fixture" | "live_model";
  model: string | null;
}

export interface PlannedAction {
  index: number;
  action: string;
  arguments: Record<string, string>;
  rationale: string;
  influenced_by: string[];
}

export interface DecisionBasis {
  kind: string;
  ref: string;
  detail: string;
}

export interface DecisionTrace {
  requested: boolean;
  effect: "allow" | "deny" | "approval_required" | "not_evaluated" | "error";
  code: string;
  reason: string;
  identity: string;
  capability: string;
  resource: string;
  source_zone: string | null;
  target_zone: string | null;
  policy_refs: string[];
  gate_refs: string[];
  approval_state: string;
  enforcement_point: string;
  coverage_surface: string;
  basis: DecisionBasis[];
}

export interface ActionCounter {
  action: string;
  attempts: number | null;
  completions: number | null;
  meaning: CounterMeaning;
}

export interface TraceEvent {
  sequence: number;
  phase: "plan" | "decision" | "attempt" | "completion" | "evidence" | "finding";
  event_type: string;
  title: string;
  detail: string;
  fields: Record<string, unknown>;
}

export interface EvidenceFinding {
  status: EvidenceStatus;
  code: string;
  message: string;
  path: string | null;
  missing_fields: string[];
}

export interface EvidencePackage {
  producer: string;
  producer_type: string;
  schema_id: string;
  events: Record<string, unknown>[];
  validation_status: EvidenceStatus;
  findings: EvidenceFinding[];
  integrity_observed: boolean | null;
  completeness_observed: boolean | null;
  limitation: string;
}

export interface ClaimInterpretation {
  claim: string;
  status: ClaimStatus;
  because: string;
  evidence_refs: string[];
  limitation: string;
}

export interface ScenarioVariant {
  id: "ungoverned" | "governed";
  title: string;
  governance_enabled: boolean;
  decisions: DecisionTrace[];
  counters: ActionCounter[];
  trace: TraceEvent[];
  evidence: EvidencePackage;
  claims: ClaimInterpretation[];
}

export interface ScenarioComparison {
  action: string;
  ungoverned: ActionCounter;
  governed: ActionCounter;
  changed: boolean;
  interpretation: string;
}

export interface ScenarioRun {
  api_version: string;
  scenario_id: string;
  run_id: string;
  title: string;
  deterministic: boolean;
  safety_boundary: string;
  planner_input: PlannerInput;
  plan: PlannedAction[];
  variants: [ScenarioVariant, ScenarioVariant];
  comparison: ScenarioComparison[];
  strongest_claim: string;
  residual_risk: string;
  restored: boolean;
}

export interface DemoOptions {
  injection_enabled: boolean;
  enforcement_enabled: boolean;
  enforcement_failure: boolean;
  failure_mode: "fail_closed" | "fail_open" | "bounded";
  identity_ref: string;
  observed_subject_revision: string | null;
  approval_state: "missing" | "valid" | "expired" | "non_human" | "wrong_revision";
  planner_mode: "deterministic" | "live";
}

export interface ContentBlock {
  id: string;
  kind:
    | "section"
    | "prose"
    | "code"
    | "concept"
    | "note"
    | "boundary"
    | "verdict"
    | "decision_table"
    | "ledger_comparison"
    | "diagnostics";
  title: string | null;
  body: string;
  language: string | null;
  rows: Record<string, unknown>[];
  metadata: Record<string, unknown>;
}

export interface StructuredLabRun {
  api_version: string;
  run_id: string;
  module_id: string;
  legacy_lab_id: string;
  title: string;
  status: "ready" | "running" | "complete" | "failed" | "unavailable";
  blocks: ContentBlock[];
  results: Record<string, unknown>;
  diagnostics: EvidenceFinding[];
  executable_checks: string[];
  completion_eligible: boolean;
  unavailable_reason: string | null;
  safety_boundary: string;
}

export interface AssessmentOption {
  id: string;
  label: string;
}

export interface PublicAssessment {
  id: string;
  module_id: string;
  kind: string;
  prompt: string;
  context: string;
  options: AssessmentOption[];
  minimum_score: number;
}

export interface AssessmentResult {
  assessment_id: string;
  module_id: string;
  score: number;
  passed: boolean;
  correct_answers: string[];
  explanation: string;
  feedback: string[];
  concepts_mastered: string[];
  concepts_needing_review: string[];
}

export interface ModuleProgress {
  module_id: string;
  status: ModuleStatus;
  executions: number;
  assessment_attempts: number;
  best_score: number | null;
  last_activity: string | null;
  concepts_mastered: string[];
  concepts_needing_review: string[];
}

export interface Dashboard {
  learner_id: string;
  modules: ModuleProgress[];
  completed_modules: number;
  total_modules: number;
  completion_percent: number;
  current_module_id: string | null;
  last_activity: string | null;
  concepts_mastered: string[];
  concepts_needing_review: string[];
  capstone_status: ModuleStatus;
}

export interface ContractSummary {
  id: string;
  name: string;
  profile: string;
  identity_count: number;
  capability_count: number;
  zone_count: number;
  gate_count: number;
  lock_status: EvidenceStatus;
}

export interface ContractNode {
  id: string;
  kind: string;
  label: string;
  detail: string;
  fields: Record<string, unknown>;
}

export interface ContractEdge {
  source: string;
  target: string;
  kind: string;
  label: string;
}

export interface ContractDetail {
  summary: ContractSummary;
  source: string;
  canonical_document: Record<string, unknown>;
  nodes: ContractNode[];
  edges: ContractEdge[];
  generated_controls: Record<string, unknown>[];
  diagnostics: EvidenceFinding[];
  formatting_limitation: string;
  assurance_boundary: string;
}

export type ContractMutationOperation =
  | "set_project_purpose"
  | "toggle_identity_capability"
  | "set_zone_share_category"
  | "set_approval_expiry"
  | "set_subject_revision"
  | "remove_evidence_field"
  | "upsert_construct"
  | "remove_construct"
  | "toggle_context_resource"
  | "toggle_policy_rule"
  | "set_profile"
  | "refresh_lock";

export type ContractConstructKind =
  | "context"
  | "agent"
  | "policy"
  | "capability"
  | "identity"
  | "approval"
  | "evidence"
  | "trust_zone"
  | "membership"
  | "protocol_target"
  | "gate"
  | "revocation"
  | "delegation"
  | "handoff"
  | "relation";

export interface ContractMutation {
  operation: ContractMutationOperation;
  target: string;
  value: unknown;
}

export interface ContractValidation {
  valid: boolean;
  source: string;
  canonical_document: Record<string, unknown> | null;
  nodes: ContractNode[];
  edges: ContractEdge[];
  diagnostics: EvidenceFinding[];
  generated_controls: Record<string, unknown>[];
  lock_status: EvidenceStatus;
  lock_refreshed: boolean;
  semantic_paths_only: boolean;
}

export interface LiveModelSettingsResponse {
  enabled: boolean;
  provider: string;
  model: string;
  configured: boolean;
  persisted: boolean;
  boundary: string;
}

export interface CapstoneDefinition {
  id: "24";
  title: string;
  summary: string;
  guidance: string[];
  requirements: string[];
  frameworks: ("framework-neutral" | "crewai" | "langgraph")[];
  failure_injections: ("prompt-injection" | "expired-approval" | "artifact-tamper" | "unauthorized-delegation" | "replay" | "bypass")[];
  assessment_id: string;
  status: ModuleStatus;
}
