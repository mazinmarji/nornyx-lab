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
  explanation: ScenarioExplanation | null;
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
  /** The concepts this item actually tests — never the whole module. */
  concepts: string[];
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
  /** Evidence granted by this attempt: the tested concepts only. */
  concepts_mastered: string[];
  concepts_needing_review: string[];
  /** Module concepts still without mastery evidence after this attempt. */
  module_concepts_pending: string[];
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
  /** Taught by this module, no mastery evidence yet. Completion ≠ mastery. */
  concepts_pending_evidence: string[];
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
  concepts_pending_evidence: string[];
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

/* ------------------------------------------------------------------ pedagogy
   The plain-language teaching layer. These carry the formal term alongside the
   plain one rather than instead of it; no canonical Nornyx field is renamed. */

export type LearnerMode = "guided" | "explore";

export type CausalStepKind =
  | "input"
  | "plan"
  | "decision"
  | "deny"
  | "block"
  | "blocked"
  | "effect"
  | "gap";

export interface CausalStep {
  label: string;
  detail: string;
  kind: CausalStepKind;
}

/** Derived from the run in explain.py — never authored per scenario. */
export interface ScenarioExplanation {
  determinate: boolean;
  headline: string;
  what_happened: string;
  why: string[];
  nornyx_role: string;
  proves: string;
  does_not_prove: string[];
  remember: string;
  causal_chain: CausalStep[];
}

export interface GlossaryTerm {
  id: string;
  term: string;
  also: string[];
  plain: string;
  why: string;
  example: string;
  formal: string;
  nornyx: string;
  stage: number;
}

export interface Glossary {
  api_version: string;
  version: string;
  terms: GlossaryTerm[];
}

export interface RemediationGuidance {
  code: string;
  title: string;
  means: string;
  matters: string;
  inspect: string;
  correction: string;
  verify: string;
}

export interface RemediationRegistry {
  api_version: string;
  version: string;
  provenance_label: string;
  unknown_code_notice: string;
  entries: RemediationGuidance[];
}

export interface OrientationIdea {
  id: string;
  number: number;
  name: string;
  headline: string;
  body: string;
  example_prompt: string;
  example_output: string;
  questions: string[];
  punchline: string;
  diagram: string;
}

export interface Orientation {
  api_version: string;
  version: string;
  id: string;
  title: string;
  subtitle: string;
  lede: string;
  minutes: number;
  ideas: OrientationIdea[];
  nornyx_position: { headline: string; body: string; boundary: string };
  closing: { headline: string; body: string; cta: string };
}

export interface StageStep {
  number: number;
  name: string;
  plain: string;
  module_ids: string[];
}

export interface CurriculumStage {
  id: string;
  number: number;
  name: string;
  question: string;
  plain: string;
  steps: StageStep[];
  completed_steps: number;
  total_steps: number;
}

export interface StageMap {
  api_version: string;
  version: string;
  entry: { module_ids: string[]; why: string };
  stages: CurriculumStage[];
  understood_concepts: string[];
  next_concepts: string[];
}

export interface PredictionOption {
  id: string;
  label: string;
}

/** Never scored. Committing to an answer is what makes the reveal land. */
export interface Prediction {
  prompt: string;
  options: PredictionOption[];
}

export interface NamedConcept {
  plain_name: string;
  formal_term: string;
  definition: string;
}

export interface LessonTeaching {
  api_version: string;
  module_id: string;
  plain_title: string;
  learn: string;
  question: string;
  why_you_care: string;
  story: string;
  prediction: Prediction;
  concept: NamedConcept;
  nornyx_role: string;
  takeaway: string;
  glossary: GlossaryTerm[];
}

/** The demo story screens are rendered by the browser; shape stays loose. */
export interface DemoStoryScreen {
  id: string;
  number: number;
  kind: "story" | "predict" | "run" | "choose" | "position" | "proof" | "limits";
  title: string;
  lede?: string;
  body?: string;
  punchline?: string;
  cta?: string;
  [key: string]: unknown;
}

export interface DemoStory {
  version: string;
  note: string;
  screens: DemoStoryScreen[];
}
