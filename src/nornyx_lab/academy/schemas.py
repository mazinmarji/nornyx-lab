"""Versioned API contracts for the browser academy.

The academy never asks the browser to infer governance outcomes from terminal
text.  These models make the important distinctions explicit: proposal versus
execution, decision versus enforcement, attempt versus completion, integrity
versus completeness, and supported versus unsupported claims.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

API_VERSION = "v1"


class AcademyModel(BaseModel):
    """Strict base model used at every public API boundary."""

    # Keep enum instances inside Python so domain code can make type-safe
    # comparisons. Pydantic/FastAPI still serialize their string values at the
    # JSON boundary.
    model_config = ConfigDict(extra="forbid")


class ModuleKind(str, Enum):
    FOUNDATION = "foundation"
    LAB = "lab"
    CAPSTONE = "capstone"


class Difficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ModuleStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    NEEDS_REVIEW = "needs_review"
    COMPLETE = "complete"


class RunStatus(str, Enum):
    READY = "ready"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class DecisionEffect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"
    NOT_EVALUATED = "not_evaluated"
    ERROR = "error"


class CounterMeaning(str, Enum):
    PREVENTED = "prevented_before_execution"
    ATTEMPTED_NOT_COMPLETED = "attempted_not_completed"
    EXECUTED = "executed"
    NOT_PLANNED = "not_planned"
    INDETERMINATE = "indeterminate"


class EvidenceStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    MISSING = "missing"
    UNKNOWN = "unknown"


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    INDETERMINATE = "indeterminate"


class BlockKind(str, Enum):
    SECTION = "section"
    PROSE = "prose"
    CODE = "code"
    CONCEPT = "concept"
    NOTE = "note"
    BOUNDARY = "boundary"
    VERDICT = "verdict"
    DECISION_TABLE = "decision_table"
    LEDGER_COMPARISON = "ledger_comparison"
    DIAGNOSTICS = "diagnostics"


class AssessmentKind(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    SCENARIO_PREDICTION = "scenario_prediction"
    ORDERING = "ordering"
    IDENTIFY_BYPASS = "identify_bypass"
    POLICY_REPAIR = "policy_repair"
    EVIDENCE_INTERPRETATION = "evidence_interpretation"
    ASSURANCE_CORRECTION = "assurance_correction"


class ConceptRef(AcademyModel):
    id: str
    name: str
    summary: str


class CompletionRule(AcademyModel):
    requires_execution: bool = True
    assessment_id: str
    minimum_score: float = Field(default=0.8, ge=0, le=1)
    required_challenges: tuple[str, ...] = ()


class CurriculumModule(AcademyModel):
    id: str
    legacy_lab_id: str | None = None
    kind: ModuleKind
    title: str
    eyebrow: str
    summary: str
    why_it_matters: str
    difficulty: Difficulty
    minutes: int = Field(gt=0)
    prerequisites: tuple[str, ...] = ()
    concepts: tuple[str, ...]
    outcomes: tuple[str, ...]
    interaction: str
    scenario_id: str | None = None
    completion: CompletionRule
    migration_classification: str | None = None
    status: ModuleStatus = ModuleStatus.NOT_STARTED
    score: float | None = Field(default=None, ge=0, le=1)


class LearningPath(AcademyModel):
    id: str
    title: str
    audience: str
    summary: str
    prerequisites: tuple[str, ...]
    estimated_minutes: int = Field(gt=0)
    concepts: tuple[str, ...]
    module_ids: tuple[str, ...]
    outcomes: tuple[str, ...]
    completion_criteria: str
    completed_modules: int = 0
    total_modules: int = 0


class CurriculumCatalog(AcademyModel):
    version: str
    modules: tuple[CurriculumModule, ...]
    paths: tuple[LearningPath, ...]
    concepts: tuple[ConceptRef, ...]


class PlannerInput(AcademyModel):
    task: str
    context: str
    context_origin: str
    context_authority: Literal["decides", "informs_only"]
    context_taint: Literal["trusted", "untrusted", "mixed"]
    planner_kind: Literal["deterministic_fixture", "live_model"]
    model: str | None = None


class PlannedAction(AcademyModel):
    index: int = Field(ge=1)
    action: str
    arguments: dict[str, str] = Field(default_factory=dict)
    rationale: str
    influenced_by: tuple[str, ...] = ()


class DecisionBasis(AcademyModel):
    kind: str
    ref: str
    detail: str = ""


class DecisionTrace(AcademyModel):
    requested: bool = True
    effect: DecisionEffect
    code: str
    reason: str
    identity: str
    capability: str
    resource: str
    source_zone: str | None = None
    target_zone: str | None = None
    policy_refs: tuple[str, ...] = ()
    gate_refs: tuple[str, ...] = ()
    approval_state: str = "not_applicable"
    enforcement_point: str
    coverage_surface: str
    basis: tuple[DecisionBasis, ...] = ()


class ActionCounter(AcademyModel):
    action: str
    attempts: int | None = Field(default=0, ge=0)
    completions: int | None = Field(default=0, ge=0)
    meaning: CounterMeaning


class TraceEvent(AcademyModel):
    sequence: int = Field(ge=1)
    phase: Literal["plan", "decision", "attempt", "completion", "evidence", "finding"]
    event_type: str
    title: str
    detail: str
    fields: dict[str, Any] = Field(default_factory=dict)


class EvidenceFinding(AcademyModel):
    status: EvidenceStatus
    code: str
    message: str
    path: str | None = None
    missing_fields: tuple[str, ...] = ()


class EvidencePackage(AcademyModel):
    producer: str
    producer_type: str
    schema_id: str
    events: tuple[dict[str, Any], ...] = ()
    validation_status: EvidenceStatus
    findings: tuple[EvidenceFinding, ...] = ()
    integrity_observed: bool | None = None
    completeness_observed: bool | None = None
    limitation: str


class ClaimInterpretation(AcademyModel):
    claim: str
    status: ClaimStatus
    because: str
    evidence_refs: tuple[str, ...] = ()
    limitation: str


class ScenarioVariant(AcademyModel):
    id: Literal["ungoverned", "governed"]
    title: str
    governance_enabled: bool
    decisions: tuple[DecisionTrace, ...]
    counters: tuple[ActionCounter, ...]
    trace: tuple[TraceEvent, ...]
    evidence: EvidencePackage
    claims: tuple[ClaimInterpretation, ...]


class ScenarioComparison(AcademyModel):
    action: str
    ungoverned: ActionCounter
    governed: ActionCounter
    changed: bool
    interpretation: str


class CausalStep(AcademyModel):
    """One link in the "because" chain shown to a learner."""

    label: str
    detail: str = ""
    kind: Literal["input", "plan", "decision", "deny", "block", "blocked", "effect", "gap"]


class ScenarioExplanation(AcademyModel):
    """The learner-facing reading of a run, derived in `explain.py`.

    `determinate` is false when the response cannot support a narrative at all —
    contradictory counters, a missing variant, no measured difference. The
    browser must render that state rather than falling back to the outcome the
    lesson expected.
    """

    determinate: bool
    headline: str
    what_happened: str
    why: tuple[str, ...]
    nornyx_role: str
    proves: str
    does_not_prove: tuple[str, ...]
    remember: str
    causal_chain: tuple[CausalStep, ...] = ()


class ScenarioRun(AcademyModel):
    api_version: str = API_VERSION
    scenario_id: str
    run_id: str
    title: str
    deterministic: bool
    safety_boundary: str
    planner_input: PlannerInput
    plan: tuple[PlannedAction, ...]
    variants: tuple[ScenarioVariant, ScenarioVariant]
    comparison: tuple[ScenarioComparison, ...]
    strongest_claim: str
    residual_risk: str
    restored: bool = True
    explanation: ScenarioExplanation | None = None


class DemoOptions(AcademyModel):
    injection_enabled: bool = True
    enforcement_enabled: bool = True
    enforcement_failure: bool = False
    failure_mode: Literal["fail_closed", "fail_open", "bounded"] = "fail_closed"
    identity_ref: str = "identity.research_assistant"
    observed_subject_revision: str | None = None
    approval_state: Literal["missing", "valid", "expired", "non_human", "wrong_revision"] = (
        "missing"
    )
    planner_mode: Literal["deterministic", "live"] = "deterministic"


class ContentBlock(AcademyModel):
    id: str
    kind: BlockKind
    title: str | None = None
    body: str = ""
    language: str | None = None
    rows: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class StructuredLabRun(AcademyModel):
    api_version: str = API_VERSION
    run_id: str
    module_id: str
    legacy_lab_id: str
    title: str
    status: RunStatus
    blocks: tuple[ContentBlock, ...]
    results: dict[str, Any]
    diagnostics: tuple[EvidenceFinding, ...] = ()
    executable_checks: tuple[str, ...] = ()
    completion_eligible: bool = False
    unavailable_reason: str | None = None
    safety_boundary: str


class AssessmentOption(AcademyModel):
    id: str
    label: str


class AssessmentDefinition(AcademyModel):
    id: str
    module_id: str
    kind: AssessmentKind
    # The concepts this item actually tests — always a proper subset of the
    # module's concepts. Passing grants mastery evidence for these and nothing
    # else; one correct answer must not substantiate a whole module.
    concepts: tuple[str, ...] = ()
    prompt: str
    context: str = ""
    options: tuple[AssessmentOption, ...]
    correct: tuple[str, ...] = Field(exclude=True)
    explanation: str
    incorrect_explanations: dict[str, str] = Field(default_factory=dict)
    minimum_score: float = Field(default=1.0, ge=0, le=1)


class PublicAssessment(AcademyModel):
    id: str
    module_id: str
    kind: AssessmentKind
    concepts: tuple[str, ...] = ()
    prompt: str
    context: str = ""
    options: tuple[AssessmentOption, ...]
    minimum_score: float = Field(default=1.0, ge=0, le=1)


class AssessmentSubmission(AcademyModel):
    answers: tuple[str, ...]


class AssessmentResult(AcademyModel):
    assessment_id: str
    module_id: str
    score: float = Field(ge=0, le=1)
    passed: bool
    correct_answers: tuple[str, ...]
    explanation: str
    feedback: tuple[str, ...]
    # Evidence granted by this attempt: only the concepts the assessment
    # declares it tests, never every concept attached to the module.
    concepts_mastered: tuple[str, ...] = ()
    concepts_needing_review: tuple[str, ...] = ()
    # Module concepts still without mastery evidence after this attempt was
    # recorded. Lets the UI say "demonstrated X; Y still needs evidence".
    module_concepts_pending: tuple[str, ...] = ()


class ModuleProgress(AcademyModel):
    module_id: str
    status: ModuleStatus
    executions: int = Field(default=0, ge=0)
    assessment_attempts: int = Field(default=0, ge=0)
    best_score: float | None = Field(default=None, ge=0, le=1)
    last_activity: str | None = None
    concepts_mastered: tuple[str, ...] = ()
    concepts_needing_review: tuple[str, ...] = ()
    # Concepts the module teaches for which no mastery evidence exists yet.
    # "Complete" module status is content completion; it does not clear this.
    concepts_pending_evidence: tuple[str, ...] = ()


class AdvancedStanding(AcademyModel):
    """The explicit advanced-completion gate, one boolean per requirement.

    ``capstone_status`` alone is content completion: a Guided run plus the
    capstone assessment. Advanced competence additionally requires
    learner-authored (Independent) capstone work and a completion-eligible run
    on the transfer scenario, so a scaffolded walkthrough can never be
    reported as independent advanced competence.
    """

    capstone_content_complete: bool = False
    capstone_concepts_demonstrated: bool = False
    independent_authorship_demonstrated: bool = False
    transfer_demonstrated: bool = False
    advanced_competence_demonstrated: bool = False
    note: str = ""


class Dashboard(AcademyModel):
    learner_id: str = "local"
    modules: tuple[ModuleProgress, ...]
    completed_modules: int
    total_modules: int
    completion_percent: float = Field(ge=0, le=100)
    current_module_id: str | None = None
    last_activity: str | None = None
    concepts_mastered: tuple[str, ...] = ()
    concepts_needing_review: tuple[str, ...] = ()
    concepts_pending_evidence: tuple[str, ...] = ()
    capstone_status: ModuleStatus = ModuleStatus.NOT_STARTED
    advanced_standing: AdvancedStanding | None = None


class ProgressExport(AcademyModel):
    schema_id: str = "nornyx.academy.progress.v1"
    generated_at: str
    learner_id: str
    dashboard: Dashboard
    assessment_history: tuple[dict[str, Any], ...]
    assurance_note: str


class ContractSummary(AcademyModel):
    id: str
    name: str
    profile: str
    identity_count: int
    capability_count: int
    zone_count: int
    gate_count: int
    lock_status: EvidenceStatus


class ContractNode(AcademyModel):
    id: str
    kind: str
    label: str
    detail: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)


class ContractEdge(AcademyModel):
    source: str
    target: str
    kind: str
    label: str = ""


class ContractDetail(AcademyModel):
    summary: ContractSummary
    source: str
    canonical_document: dict[str, Any]
    nodes: tuple[ContractNode, ...]
    edges: tuple[ContractEdge, ...]
    generated_controls: tuple[dict[str, Any], ...]
    diagnostics: tuple[EvidenceFinding, ...]
    formatting_limitation: str
    assurance_boundary: str


class ContractMutation(AcademyModel):
    operation: Literal[
        "set_project_purpose",
        "toggle_identity_capability",
        "set_zone_share_category",
        "set_approval_expiry",
        "set_subject_revision",
        "remove_evidence_field",
        "upsert_construct",
        "remove_construct",
        "toggle_context_resource",
        "toggle_policy_rule",
        "set_profile",
        "refresh_lock",
    ]
    target: str
    value: Any


class ContractWorkbenchRequest(AcademyModel):
    contract_id: Literal["atlas", "ledger"]
    mutations: tuple[ContractMutation, ...] = ()


class ContractValidation(AcademyModel):
    valid: bool
    source: str
    canonical_document: dict[str, Any] | None = None
    nodes: tuple[ContractNode, ...] = ()
    edges: tuple[ContractEdge, ...] = ()
    diagnostics: tuple[EvidenceFinding, ...]
    generated_controls: tuple[dict[str, Any], ...] = ()
    lock_status: EvidenceStatus = EvidenceStatus.UNKNOWN
    lock_refreshed: bool = False
    semantic_paths_only: bool = True


class LiveModelSettingsRequest(AcademyModel):
    enabled: bool = False
    provider: Literal["anthropic"] = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key: SecretStr | None = None


class LiveModelSettingsResponse(AcademyModel):
    enabled: bool
    provider: str
    model: str
    configured: bool
    persisted: bool = False
    boundary: str


class CapstoneScenarioInfo(AcademyModel):
    """One deterministic capstone scenario the learner can design against.

    The transfer scenario exists so independent competence is demonstrated on a
    situation that is not the guided default: same lock-verified contract, a
    different workflow with a different consequential boundary.
    """

    id: str
    title: str
    summary: str
    consequential_action: str
    actions: tuple[str, ...]
    expected_capabilities: dict[str, str] = Field(default_factory=dict)
    declared_identities: tuple[str, ...] = ()
    declared_zones: tuple[str, ...] = ()
    declared_delegations: tuple[str, ...] = ()
    declared_handoffs: tuple[str, ...] = ()


class CapstoneDefinition(AcademyModel):
    id: Literal["24"] = "24"
    title: str
    summary: str
    guidance: tuple[str, ...]
    requirements: tuple[str, ...]
    frameworks: tuple[Literal["framework-neutral", "crewai", "langgraph"], ...]
    failure_injections: tuple[
        Literal[
            "prompt-injection",
            "expired-approval",
            "artifact-tamper",
            "unauthorized-delegation",
            "replay",
            "bypass",
        ],
        ...,
    ]
    scenarios: tuple[CapstoneScenarioInfo, ...] = ()
    assessment_id: str = "assessment.24"
    status: ModuleStatus = ModuleStatus.NOT_STARTED


class CapstoneRunRequest(AcademyModel):
    framework: Literal["framework-neutral", "crewai", "langgraph"] = "framework-neutral"
    failure_injection: Literal[
        "prompt-injection",
        "expired-approval",
        "artifact-tamper",
        "unauthorized-delegation",
        "replay",
        "bypass",
    ] = "prompt-injection"
    scaffolding: Literal["guided", "reduced", "independent"] = "guided"
    scenario: Literal["customer-remediation", "refund-disbursement"] = "customer-remediation"
    # Learner-authored design sections. None means "not provided": Guided mode
    # may fall back to the academy's scaffolded defaults, Reduced/Independent
    # scaffolding require the learner to supply them. Deep validation stays in
    # capstone.py so the CLI/module path applies identical rules.
    roles: tuple[dict[str, Any], ...] | None = None
    trust_zones: dict[str, Any] | None = None
    coordination: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None
    assurance: dict[str, Any] | None = None


class PlatformInfo(AcademyModel):
    api_version: str = API_VERSION
    academy_version: str
    nornyx_runtime_version: str
    nornyx_audited_main_commit: str
    nornyx_main_delta: str
    adapter_version: str
    spi_version: str
    deterministic_offline: bool = True
    default_actions_are_inert: bool = True
    assurance_tier_ceiling: str = "Tier 2 on named cooperative in-process surfaces"


class Health(AcademyModel):
    status: Literal["ok"] = "ok"
    api_version: str = API_VERSION


# ---------------------------------------------------------------- pedagogy
# Presentation-layer teaching structures. None of these rename or replace a
# canonical Nornyx field; they carry the plain-language layer the learner reads
# first, with the formal term kept alongside rather than instead.


class LearnerMode(str, Enum):
    """How much implementation detail a learner has asked to see."""

    GUIDED = "guided"
    EXPLORE = "explore"


class GlossaryTerm(AcademyModel):
    id: str
    term: str
    also: tuple[str, ...] = ()
    plain: str
    why: str
    example: str
    formal: str
    nornyx: str
    stage: int = Field(ge=1, le=7)


class Glossary(AcademyModel):
    api_version: str = API_VERSION
    version: str
    terms: tuple[GlossaryTerm, ...]


class RemediationGuidance(AcademyModel):
    """Authored guidance for one diagnostic code.

    Five parts, all required. `verify` is the part that keeps this honest: it
    names what to re-run and what evidence would support closure, so guidance
    reads as a hypothesis to test rather than an instruction that settles the
    matter. Nothing here may claim an outcome — whether a correction worked is
    observed from a re-run, never asserted by authored text.
    """

    code: str
    title: str
    means: str
    matters: str
    inspect: str
    correction: str
    verify: str


class RemediationRegistry(AcademyModel):
    """The registry, fetched separately from any run result.

    Separate on purpose. Guidance is academy teaching material, not part of a
    Nornyx decision payload, and shipping it inside one would invite exactly the
    confusion the provenance label exists to prevent. Adding codes grows
    `entries` without changing this contract.
    """

    api_version: str = API_VERSION
    version: str
    provenance_label: str
    unknown_code_notice: str
    entries: tuple[RemediationGuidance, ...]


class OrientationIdea(AcademyModel):
    id: str
    number: int = Field(ge=1)
    name: str
    headline: str
    body: str
    example_prompt: str = ""
    example_output: str = ""
    questions: tuple[str, ...] = ()
    punchline: str
    diagram: str


class NornyxPosition(AcademyModel):
    headline: str
    body: str
    boundary: str


class OrientationClosing(AcademyModel):
    headline: str
    body: str
    cta: str


class Orientation(AcademyModel):
    api_version: str = API_VERSION
    version: str
    id: str
    title: str
    subtitle: str
    lede: str
    minutes: int = Field(gt=0)
    ideas: tuple[OrientationIdea, ...]
    nornyx_position: NornyxPosition
    closing: OrientationClosing


class StageStep(AcademyModel):
    number: int = Field(ge=1)
    name: str
    plain: str
    module_ids: tuple[str, ...]


class CurriculumStage(AcademyModel):
    id: str
    number: int = Field(ge=1, le=7)
    name: str
    question: str
    plain: str
    steps: tuple[StageStep, ...]
    completed_steps: int = 0
    total_steps: int = 0


class StageEntry(AcademyModel):
    module_ids: tuple[str, ...]
    why: str


class StageMap(AcademyModel):
    api_version: str = API_VERSION
    version: str
    entry: StageEntry
    stages: tuple[CurriculumStage, ...]
    understood_concepts: tuple[str, ...] = ()
    next_concepts: tuple[str, ...] = ()


class PredictionOption(AcademyModel):
    id: str = ""
    label: str


class Prediction(AcademyModel):
    """Never scored. Its only job is to make the learner commit before the reveal."""

    prompt: str
    options: tuple[PredictionOption, ...]


class NamedConcept(AcademyModel):
    plain_name: str
    formal_term: str
    definition: str = ""


class LessonTeaching(AcademyModel):
    """The A-L scaffold for one module."""

    api_version: str = API_VERSION
    module_id: str
    # Plain-language heading shown in Guided mode. The repository's own module
    # title is unchanged and remains the Explore heading and the deep link.
    plain_title: str
    learn: str
    question: str
    why_you_care: str
    story: str
    prediction: Prediction
    concept: NamedConcept
    nornyx_role: str
    takeaway: str
    glossary: tuple[GlossaryTerm, ...] = ()
