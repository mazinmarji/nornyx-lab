import { Link } from "react-router-dom";
import type { CurriculumModule } from "../types";

interface WorkbenchDestination {
  expectedInteraction: string;
  route: string;
  workbench: string;
  heading: string;
  description: string;
}

const MODULE_DESTINATIONS: Record<string, WorkbenchDestination> = {
  F0: { expectedInteraction: "governed-ungoverned-demo", route: "/demo", workbench: "five-minute demo", heading: "Compare governed and ungoverned execution", description: "Run the academy's visual side-by-side scenario and inspect the decision, counters, and evidence without using a terminal." },
  F1: { expectedInteraction: "model-variability-lab", route: "/diagnostics", workbench: "diagnostics workbench", heading: "Read variability as evidence", description: "Practice separating an observed result from a supported claim, then inspect how the academy reports pass, fail, missing, and unknown evidence." },
  F2: { expectedInteraction: "context-composer", route: "/demo", workbench: "five-minute demo", heading: "See untrusted context reach a planner", description: "Use the visual demo to follow retrieved instructions through planning and compare the effects of an enforced boundary." },
  F3: { expectedInteraction: "tool-side-effect-simulator", route: "/graph", workbench: "authority graph", heading: "Trace identity to reachable authority", description: "Explore identities, capabilities, trust zones, and policy links on the academy's interactive graph." },
  F4: { expectedInteraction: "agent-runtime-graph", route: "/graph", workbench: "authority graph", heading: "Explore the runtime as a graph", description: "Use the graph view to build a mental model of agents, authority, policy, and boundaries before comparing runtime patterns here." },
  F5: { expectedInteraction: "evaluation-workbench", route: "/diagnostics", workbench: "diagnostics workbench", heading: "Practice evidence-based evaluation", description: "Filter concrete findings and distinguish a passing check from a broader assurance claim." },
  "00": { expectedInteraction: "assistant-agent-simulator", route: "/demo", workbench: "five-minute demo", heading: "Compare text generation with reachable effects", description: "Use the side-by-side demo to see when untrusted instructions remain text and when attached tools make effects reachable." },
  "01": { expectedInteraction: "control-drift-diff", route: "/contracts", workbench: "contract explorer", heading: "Inspect one authoritative control source", description: "Open the checked contracts and compare source, generated controls, object relationships, and validation findings." },
  "02": { expectedInteraction: "claim-layer-sorter", route: "/evidence", workbench: "evidence explorer", heading: "Match claims to the evidence they need", description: "Inspect decision traces, observations, validation results, and limitations without treating them as interchangeable proof." },
  "03": { expectedInteraction: "pdp-pep-wiring-canvas", route: "/graph", workbench: "authority graph", heading: "Locate decision and enforcement boundaries", description: "Follow policy and capability links in the graph, then use this lesson's structured run to compare enforced and bypassed paths." },
  "04": { expectedInteraction: "identity-authority-graph", route: "/graph", workbench: "authority graph", heading: "Explore identity and authority relationships", description: "Navigate the academy's identities, agents, capabilities, zones, policies, and gates as a connected system." },
  "05": { expectedInteraction: "trust-zone-injection", route: "/demo", workbench: "five-minute demo", heading: "Watch a trust-zone gate stop an effect", description: "Run the visual governed-versus-ungoverned comparison and inspect both capability and zone-crossing decisions." },
  "06": { expectedInteraction: "decision-matrix", route: "/approvals", workbench: "approval simulator", heading: "Vary a bounded approval assertion", description: "Change actor, action, evidence, revision, and time fields in a guided form and read the exact decision result." },
  "07": { expectedInteraction: "composition-layer-view", route: "/contracts", workbench: "contract explorer", heading: "Trace composed controls to their source", description: "Inspect profiles, modules, generated controls, and relationships while keeping provenance visible." },
  "08": { expectedInteraction: "approval-simulator", route: "/approvals", workbench: "approval simulator", heading: "Test approval as a bounded assertion", description: "Use labelled controls to compare valid, missing, stale, mismatched, and otherwise invalid approval evidence." },
  "09": { expectedInteraction: "enforcement-failure-lab", route: "/diagnostics", workbench: "diagnostics workbench", heading: "Inspect failure semantics", description: "Practice reading exact failure codes and missing evidence before the structured lesson compares fail-open, fail-closed, and bounded degradation." },
  "10": { expectedInteraction: "evidence-explorer", route: "/evidence", workbench: "evidence explorer", heading: "Inspect a bound evidence stream", description: "Explore decisions, observations, event order, artifact bindings, and validation status in a purpose-built evidence view." },
  "11": { expectedInteraction: "lock-replay-workbench", route: "/evidence", workbench: "evidence explorer", heading: "Look for drift, replay, and duplication", description: "Use the evidence view to distinguish content binding from occurrence and sequence integrity." },
  "12": { expectedInteraction: "assurance-claim-editor", route: "/evidence", workbench: "evidence explorer", heading: "Calibrate assurance claims", description: "Compare each claim with its named mechanism, evidence references, and explicit limitation." },
  "13": { expectedInteraction: "bypass-explorer", route: "/diagnostics", workbench: "diagnostics workbench", heading: "Find uncovered paths", description: "Inspect coverage findings and negative controls without implying that a cooperative wrapper governs every route." },
  "14": { expectedInteraction: "visual-contract-builder", route: "/builder", workbench: "visual contract builder", heading: "Author a contract visually", description: "Use guided forms to stage contract changes, validate them, and compare synchronized source and graph views—without editing raw YAML." },
  "15": { expectedInteraction: "profile-lock-workbench", route: "/contracts", workbench: "contract explorer", heading: "Inspect profiles and locks separately", description: "Compare profile provenance, generated artifacts, and exact lock bindings in the contract explorer." },
  "16": { expectedInteraction: "authorization-request-workbench", route: "/contracts", workbench: "contract explorer", heading: "Inspect the assured authorization surface", description: "Explore the lock-verified contract and its identities, capabilities, policies, and generated controls before running typed requests here." },
  "17": { expectedInteraction: "occurrence-drift-timeline", route: "/evidence", workbench: "evidence explorer", heading: "Follow occurrence-aware evidence", description: "Inspect ordered events and their bindings, then use this lesson to distinguish missions, operations, occurrences, and attempts." },
  "18": { expectedInteraction: "crewai-adapter-lab", route: "/diagnostics", workbench: "diagnostics workbench", heading: "Review adapter coverage precisely", description: "Use concrete diagnostics to separate supported tool-call coverage from unsupported or unwrapped framework paths." },
  "19": { expectedInteraction: "langgraph-occurrence-suite", route: "/graph", workbench: "authority graph", heading: "Orient the LangGraph exercise", description: "Review identities, capabilities, and gates visually, then run the full pinned runtime suite on this lesson page." },
  "20": { expectedInteraction: "conformance-supply-chain-lab", route: "/diagnostics", workbench: "diagnostics workbench", heading: "Separate conformance from supply-chain evidence", description: "Filter concrete checks and limitations before this lesson runs its conformance and inert package-inspection exercises." },
  "21": { expectedInteraction: "authoring-ci-pipeline", route: "/builder", workbench: "visual contract builder", heading: "Start with a checked contract change", description: "Stage and validate a visual contract mutation, then use this lesson's structured run to inspect the remaining delivery gates." },
  "22": { expectedInteraction: "forge-release-network", route: "/graph", workbench: "authority graph", heading: "Explore separation of duties", description: "Inspect the network shape visually, then vary approval and bypass evidence below before running the executable Forge workflow." },
  "23": { expectedInteraction: "assurance-audit-workbench", route: "/evidence", workbench: "evidence explorer", heading: "Review an assurance package", description: "Use the evidence explorer to practice claim-to-evidence reasoning, then generate the threat and audit records in this lesson." },
  "24": { expectedInteraction: "capstone-workspace", route: "/capstone", workbench: "capstone workspace", heading: "Design and defend your own workflow", description: "Open the learner-authored workspace to configure, run, break, validate, and defend a Northstar multi-agent design." },
};

const INTERACTION_FALLBACKS: Record<string, Omit<WorkbenchDestination, "expectedInteraction">> = {
  "approval-simulator": { route: "/approvals", workbench: "approval simulator", heading: "Practice with bounded approvals", description: "Use the guided approval form and inspect the exact decision result." },
  "visual-contract-builder": { route: "/builder", workbench: "visual contract builder", heading: "Author a checked contract visually", description: "Stage and validate contract changes through guided controls." },
  "identity-authority-graph": { route: "/graph", workbench: "authority graph", heading: "Explore the authority graph", description: "Inspect identities, capabilities, zones, policies, and gates as a connected system." },
  "evidence-explorer": { route: "/evidence", workbench: "evidence explorer", heading: "Inspect structured evidence", description: "Explore decisions, observations, bindings, validation, and limitations." },
  "capstone-workspace": { route: "/capstone", workbench: "capstone workspace", heading: "Build your capstone", description: "Configure and defend a learner-authored multi-agent workflow." },
};

const DEFAULT_DESTINATION: Omit<WorkbenchDestination, "expectedInteraction"> = {
  route: "/diagnostics",
  workbench: "diagnostics workbench",
  heading: "Inspect the lesson's evidence",
  description: "Use the diagnostics view to practice reading exact findings, status, and limitations.",
};

export function lessonInteractionFor(moduleId: string, interaction: string): Omit<WorkbenchDestination, "expectedInteraction"> {
  const exact = MODULE_DESTINATIONS[moduleId];
  if (exact?.expectedInteraction === interaction) return exact;
  return INTERACTION_FALLBACKS[interaction] ?? DEFAULT_DESTINATION;
}

function activityName(interaction: string): string {
  const preferredNames: Record<string, string> = {
    agent: "Agent",
    ai: "AI",
    ci: "CI",
    crewai: "CrewAI",
    langgraph: "LangGraph",
    pdp: "PDP",
    pep: "PEP",
  };
  return interaction
    .split("-")
    .map((word) => preferredNames[word] ?? `${word[0]?.toUpperCase() ?? ""}${word.slice(1)}`)
    .join(" ");
}

export function LessonInteraction({ module }: { module: CurriculumModule }) {
  const destination = lessonInteractionFor(module.id, module.interaction);
  return (
    <section className="lesson-interaction" aria-labelledby="lesson-interaction-heading">
      <div className="lesson-interaction-copy">
        <p className="eyebrow">Guided practice</p>
        <h2 id="lesson-interaction-heading">{destination.heading}</h2>
        <p>{destination.description}</p>
        <p className="activity-label"><span>Activity focus</span><strong>{activityName(module.interaction)}</strong></p>
      </div>
      <div className="lesson-interaction-action">
        <Link className="button button-secondary" to={destination.route}>Open {destination.workbench}</Link>
        <p><strong>Separate practice surface:</strong> choices there do not change the inputs or result of the structured lesson run below.</p>
      </div>
    </section>
  );
}

export function initialAdvancedConfiguration(moduleId: string): Record<string, unknown> {
  if (moduleId === "22") return { approval_state: "valid", include_inert_bypass: true };
  if (moduleId === "23") return { include_direct_bypass: true };
  return {};
}

export function hasAdvancedConfiguration(moduleId: string): boolean {
  return moduleId === "22" || moduleId === "23";
}

export function hasLessonConfiguration(moduleId: string): boolean {
  return /^F[1-5]$/.test(moduleId) || hasAdvancedConfiguration(moduleId);
}

interface AdvancedLessonControlsProps {
  moduleId: string;
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}

export function AdvancedLessonControls({ moduleId, value, onChange }: AdvancedLessonControlsProps) {
  const set = (key: string, next: unknown) => onChange({ ...value, [key]: next });
  if (moduleId === "19") {
    return (
      <section className="control-panel" aria-labelledby="advanced-controls-heading">
        <p className="eyebrow">Coverage in this run</p>
        <h2 id="advanced-controls-heading">One comprehensive LangGraph suite</h2>
        <div className="coverage-list" aria-label="Runtime patterns included">
          {['denial', 'retry', 'loop', 'parallel', 'interrupt', 'resume'].map((item) => <span key={item}>{item}</span>)}
        </div>
        <p className="muted">This exercise accepts no learner input fields. It requests the complete pinned suite so denial and occurrence coverage cannot be accidentally omitted; if the exact runtime is unavailable, the result says so instead of showing fallback output.</p>
      </section>
    );
  }
  if (moduleId === "22") {
    return (
      <section className="control-panel" aria-labelledby="advanced-controls-heading">
        <div className="section-heading"><div><p className="eyebrow">Guided interaction</p><h2 id="advanced-controls-heading">Change the Forge release evidence</h2></div><button type="button" className="text-button" onClick={() => onChange(initialAdvancedConfiguration(moduleId))}>Restore defaults</button></div>
        <div className="form-grid">
          <label><span>Approval evidence</span><select value={String(value.approval_state)} onChange={(event) => set("approval_state", event.target.value)}><option value="valid">Valid human approval</option><option value="missing">Approval is missing</option><option value="non_human">Non-human assertion</option></select><small>Only a valid, bounded human approval can satisfy the release gate.</small></label>
          <label className="toggle-field"><input type="checkbox" checked={Boolean(value.include_inert_bypass)} onChange={(event) => set("include_inert_bypass", event.target.checked)} /><span><strong>Include the direct-bypass negative control</strong><small>Attempt an in-memory bypass so the report can show that this route is outside the governed wrapper.</small></span></label>
        </div>
        <p className="muted">These values select deterministic, in-memory fixtures. No release, network request, credential, or external effect is reachable.</p>
      </section>
    );
  }
  if (moduleId === "23") {
    return (
      <section className="control-panel" aria-labelledby="advanced-controls-heading">
        <div className="section-heading"><div><p className="eyebrow">Guided interaction</p><h2 id="advanced-controls-heading">Choose the audit package coverage</h2></div><button type="button" className="text-button" onClick={() => onChange(initialAdvancedConfiguration(moduleId))}>Restore defaults</button></div>
        <label className="toggle-field advanced-single-toggle"><input type="checkbox" checked={Boolean(value.include_direct_bypass)} onChange={(event) => set("include_direct_bypass", event.target.checked)} /><span><strong>Include the direct-bypass negative control</strong><small>Add an inert uncovered route to the threat matrix and claim register so the resulting limitation remains visible.</small></span></label>
        <p className="muted">The bypass is a deterministic teaching fixture. It cannot publish, call a model, use credentials, or reach the network.</p>
      </section>
    );
  }
  return null;
}
