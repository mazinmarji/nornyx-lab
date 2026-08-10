import { useEffect, useMemo, useState } from "react";
import { academyApi } from "../api/client";
import { AssessmentPanel } from "../components/AssessmentPanel";
import { ContentBlocks, Findings } from "../components/ContentBlocks";
import { ErrorNotice, InfoNotice, LoadingState } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useAsyncTask } from "../components/useAsyncTask";
import { useAcademy } from "../context/AcademyContext";
import type { AdvancedStanding, CapstoneDefinition, CapstoneScenarioInfo, StructuredLabRun } from "../types";

/**
 * What each scaffolding level means for the learner. Guided is a scaffolded
 * walkthrough and says so; only Independent work can count toward advanced
 * competence, and only together with the transfer scenario.
 */
const SCAFFOLD_MEANING: Record<string, string> = {
  guided:
    "Learn how the pieces fit. The academy supplies a working starting design; running it teaches the structure but is not evidence of independent competence.",
  reduced:
    "You make the governance decisions: allocate each workflow step to an identity and capability, and set the approval policy. The academy still frames the workflow.",
  independent:
    "You author the whole design — allocations, coordination, policy, and the assurance claim. Completion-eligible Independent work on the transfer scenario is what advanced standing requires.",
};

const ACTION_LABELS: Record<string, string> = {
  read_case: "Read the customer case",
  analyze_case: "Analyze the case",
  propose_refund: "Propose a refund",
  request_approval: "Request human approval",
  notify_customer: "Notify the customer (external boundary)",
  issue_refund: "Issue the refund (money moves)",
  close_case: "Close the case",
};

interface RoleRow {
  action: string;
  identity_ref: string;
  capability_ref: string;
}

function emptyRoles(scenario: CapstoneScenarioInfo): RoleRow[] {
  return scenario.actions.map((action) => ({ action, identity_ref: "", capability_ref: "" }));
}

/**
 * The four policy decisions, every one made by the learner in Reduced and
 * Independent mode. None is pre-answered: a pre-checked box the learner never
 * touched would be academy authorship reported as learner authorship — the
 * exact overclaim the scaffolding levels exist to prevent. Each starts unset
 * and the run stays blocked until the learner has decided all of them.
 */
const POLICY_QUESTIONS = [
  {
    key: "require_external_approval",
    label: "Require a human approval before the consequential action?",
  },
  {
    key: "require_handoff_approval",
    label: "Require approval on the closure handoff?",
  },
  {
    key: "require_integrity_preflight",
    label: "Run the artifact-integrity preflight before executing?",
  },
] as const;

type PolicyAnswer = "" | "yes" | "no";
type PolicyChoices = Record<(typeof POLICY_QUESTIONS)[number]["key"], PolicyAnswer>;

const UNANSWERED_POLICY: PolicyChoices = {
  require_external_approval: "",
  require_handoff_approval: "",
  require_integrity_preflight: "",
};

/**
 * The learner's explicit decision that a design declares no delegation (or no
 * handoff). Distinct from "" (undecided): undecided blocks the run, while
 * NONE_REF is a real governance choice submitted as an explicit null with the
 * matching requirement disabled — one compound decision.
 */
const NONE_REF = "__none__";

function AdvancedStandingPanel({ standing }: { standing: AdvancedStanding }) {
  const rows: [string, boolean][] = [
    ["Capstone content complete (any scaffolding + assessment)", standing.capstone_content_complete],
    ["Capstone concepts demonstrated", standing.capstone_concepts_demonstrated],
    ["Independent learner-authored capstone", standing.independent_authorship_demonstrated],
    ["Transfer scenario completed (not the guided default)", standing.transfer_demonstrated],
  ];
  return (
    <section className="advanced-standing" data-testid="advanced-standing">
      <div className="section-heading compact-heading">
        <div>
          <p className="eyebrow">Advanced competence</p>
          <h2>{standing.advanced_competence_demonstrated ? "Demonstrated" : "Not yet demonstrated"}</h2>
        </div>
        <StatusBadge status={standing.advanced_competence_demonstrated ? "complete" : "in_progress"} />
      </div>
      <ul className="advanced-requirements">
        {rows.map(([label, satisfied]) => (
          <li key={label} className={satisfied ? "is-satisfied" : ""}>
            <span aria-hidden="true">{satisfied ? "✓" : "→"}</span>
            {label}
          </li>
        ))}
      </ul>
      {/* Says "again", not "never" — the learner did the work, and being told
          otherwise would be its own false claim. */}
      {standing.requires_redemonstration ? (
        <p className="muted" data-testid="advanced-standing-redemonstration">
          Some of this was demonstrated under an older competence definition. That work is
          still recorded, but it has to be demonstrated again before it counts towards
          advanced standing.
        </p>
      ) : null}
      <p className="muted">{standing.note}</p>
    </section>
  );
}

export function CapstonePage() {
  const definition = useAsyncTask<CapstoneDefinition>();
  const run = useAsyncTask<StructuredLabRun>();
  const { dashboard, refreshProgress } = useAcademy();
  const [framework, setFramework] = useState("framework-neutral");
  const [failure, setFailure] = useState("prompt-injection");
  const [scaffolding, setScaffolding] = useState("guided");
  const [scenarioId, setScenarioId] = useState("customer-remediation");
  const [roles, setRoles] = useState<RoleRow[]>([]);
  // "" = not yet decided. The learner must choose, not inherit — this holds
  // for every design control: policy, coordination, and trust zones alike.
  // Preselected values would reach the backend as manufactured authorship.
  const [approvalMode, setApprovalMode] = useState("");
  const [policyChoices, setPolicyChoices] = useState<PolicyChoices>(UNANSWERED_POLICY);
  const [sourceZone, setSourceZone] = useState("");
  const [targetZone, setTargetZone] = useState("");
  // Three states: "" undecided · NONE_REF the learner's explicit decision to
  // declare no delegation/handoff · otherwise a declared ref. Selecting a ref
  // is one compound choice: it both names the ref and requires it.
  const [delegationId, setDelegationId] = useState("");
  const [handoffId, setHandoffId] = useState("");
  const [claim, setClaim] = useState("");
  const [residualRisk, setResidualRisk] = useState("");
  const [falsification, setFalsification] = useState("");

  useEffect(() => { void definition.run(() => academyApi.capstone()); }, []); // stable task

  const scenario = useMemo(
    () => definition.data?.scenarios.find((item) => item.id === scenarioId) ?? null,
    [definition.data, scenarioId],
  );
  const authoring = scaffolding !== "guided";
  const independent = scaffolding === "independent";

  // Reset the design worksheet whenever the design space changes: no decision
  // — allocation, policy, coordination, or zone — may silently carry from one
  // scenario or scaffolding level into another.
  useEffect(() => {
    if (scenario) setRoles(emptyRoles(scenario));
    setApprovalMode("");
    setPolicyChoices(UNANSWERED_POLICY);
    setSourceZone("");
    setTargetZone("");
    setDelegationId("");
    setHandoffId("");
  }, [scenarioId, scaffolding, definition.data]); // scenario derives from these

  const identityOptions = scenario?.declared_identities ?? [];
  const capabilityOptions = useMemo(
    () => [...new Set(Object.values(scenario?.expected_capabilities ?? {}))],
    [scenario],
  );

  const rolesComplete = roles.every((row) => row.identity_ref && row.capability_ref);
  const policyComplete =
    approvalMode !== "" && POLICY_QUESTIONS.every((question) => policyChoices[question.key] !== "");
  const zonesApplicable = Boolean(scenario?.declared_zones.length);
  const coordinationComplete = delegationId !== "" && handoffId !== "";
  const zonesComplete = !zonesApplicable || (sourceZone !== "" && targetZone !== "");
  const assuranceComplete = claim.trim().length >= 20 && residualRisk.trim().length >= 20 && falsification.trim().length >= 20;
  const canRun =
    !authoring ||
    (rolesComplete &&
      policyComplete &&
      (!independent || (coordinationComplete && zonesComplete && assuranceComplete)));

  function buildRequest(): Record<string, unknown> {
    const request: Record<string, unknown> = {
      framework,
      failure_injection: failure,
      scaffolding,
      scenario: scenarioId,
    };
    if (!authoring) return request;
    request.roles = roles.map((row, index) => ({
      id: `${row.action}-${index + 1}`,
      role: ACTION_LABELS[row.action] ?? row.action,
      identity_ref: row.identity_ref,
      capability_ref: row.capability_ref,
      action: row.action,
    }));
    // Every value here is a decision the learner made in the form. Constants
    // would let a field-complete section reach the backend as manufactured
    // authorship: API completeness ≠ learner authorship.
    request.policy = {
      approval_mode: approvalMode,
      require_external_approval: policyChoices.require_external_approval === "yes",
      require_handoff_approval: policyChoices.require_handoff_approval === "yes",
      require_integrity_preflight: policyChoices.require_integrity_preflight === "yes",
    };
    if (independent) {
      // Compound learner choice per ref (documented, tested): choosing a
      // declared ref both names it and requires it; choosing "None" submits
      // an explicit null with the requirement disabled. Undecided ("") never
      // reaches here — the run is blocked until both are decided.
      request.coordination = {
        delegation_id: delegationId === NONE_REF ? null : delegationId,
        handoff_id: handoffId === NONE_REF ? null : handoffId,
        require_delegation: delegationId !== NONE_REF,
        require_handoff: handoffId !== NONE_REF,
      };
      if (zonesApplicable) {
        request.trust_zones = { source_zone: sourceZone, target_zone: targetZone };
      }
      request.assurance = {
        claim: claim.trim(),
        residual_risk: residualRisk.trim(),
        falsification_condition: falsification.trim(),
      };
    }
    return request;
  }

  async function runCapstone() {
    const result = await run.run(() => academyApi.runCapstone(buildRequest()));
    if (result) await refreshProgress().catch(() => undefined);
  }

  const title = typeof definition.data?.title === "string" ? definition.data.title : "Govern a multi-agent delivery workflow";
  const summary = typeof definition.data?.summary === "string" ? definition.data.summary : null;
  const guidance = Array.isArray(definition.data?.guidance) ? definition.data.guidance.filter((item): item is string => typeof item === "string") : [];
  const requirements = Array.isArray(definition.data?.requirements) ? definition.data.requirements.filter((item): item is string => typeof item === "string") : [];

  return (
    <div className="page capstone-page">
      <header className="page-header capstone-header"><div><p className="eyebrow">Capstone workspace</p><h1>{title}</h1><p>{summary ?? "Configure, execute, and assess a realistic multi-agent workflow through the connected academy service."}</p></div>{definition.data?.status ? <StatusBadge status={definition.data.status} /> : null}</header>
      {definition.data?.status === "complete" ? (
        <p className="muted capstone-status-note">
          “Complete” here is content completion — the capstone ran and its assessment was passed.
          Advanced competence is tracked separately below and requires independent authorship plus
          the transfer scenario.
        </p>
      ) : null}
      {definition.loading ? <LoadingState label="Loading capstone definition…" /> : null}
      {definition.error ? <ErrorNotice title="Capstone API unavailable" message={`${definition.error} The workspace will not substitute a mock capstone.`} onRetry={() => void definition.run(() => academyApi.capstone())} /> : null}
      {definition.data ? <>
        <section className="capstone-map" aria-label="Capstone control map"><article><span>01</span><h2>Separate identities</h2><p>Builder, reviewer, release agent, and approver carry distinct capabilities.</p></article><article><span>02</span><h2>Cross boundaries</h2><p>Trusted source and untrusted input move through explicit trust zones and handoffs.</p></article><article><span>03</span><h2>Enforce gates</h2><p>Approval, separation of duties, integrity, and runtime binding control tool paths.</p></article><article><span>04</span><h2>Defend a claim</h2><p>Evidence supports a scoped assurance statement with residual risk.</p></article></section>
        <section className="capstone-layout">
          <div className="capstone-brief"><p className="eyebrow">Service-provided brief</p><h2>Requirements</h2>{requirements.length ? <ul>{requirements.map((item) => <li key={item}>{item}</li>)}</ul> : <p>The service did not enumerate requirement text.</p>}{guidance.length ? <details open={scaffolding === "guided"}><summary>Beginner guidance</summary><ol>{guidance.map((item) => <li key={item}>{item}</li>)}</ol></details> : null}
            {dashboard?.advanced_standing ? <AdvancedStandingPanel standing={dashboard.advanced_standing} /> : null}
          </div>
          <form className="capstone-config" onSubmit={(event) => { event.preventDefault(); void runCapstone(); }}>
            <p className="eyebrow">Execution configuration</p><h2>Configure the run</h2>
            <label><span>Scenario</span><select value={scenarioId} onChange={(event) => setScenarioId(event.target.value)}>{definition.data.scenarios.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}</select>{scenario ? <small>{scenario.summary}</small> : null}</label>
            <label><span>Scaffolding</span><select value={scaffolding} onChange={(event) => setScaffolding(event.target.value)}><option value="guided">Guided (scaffolded walkthrough)</option><option value="reduced">Reduced (you allocate and set policy)</option><option value="independent">Independent (you author everything)</option></select><small data-testid="scaffolding-meaning">{SCAFFOLD_MEANING[scaffolding]}</small></label>
            <label><span>Framework surface</span><select value={framework} onChange={(event) => setFramework(event.target.value)}>{definition.data.frameworks.map((item) => <option value={item} key={item}>{item === "framework-neutral" ? "Framework-neutral" : `${item === "crewai" ? "CrewAI" : "LangGraph"} adapter`}</option>)}</select></label>
            <label><span>Controlled failure</span><select value={failure} onChange={(event) => setFailure(event.target.value)}>{definition.data.failure_injections.map((item) => <option value={item} key={item}>{item.replaceAll("-", " ")}</option>)}</select></label>

            {authoring && scenario ? (
              <fieldset className="capstone-design-form" data-testid="capstone-design-form">
                <legend>Your governance design</legend>
                <p className="muted">
                  Allocate each workflow step to a declared identity and capability. The design
                  review will tell you — with real Nornyx decisions — whether your allocation
                  holds.
                </p>
                {roles.map((row, index) => (
                  <div className="design-role-row" key={row.action}>
                    <span className="design-action">{ACTION_LABELS[row.action] ?? row.action}</span>
                    <label><span className="sr-only">{`Identity for ${row.action}`}</span>
                      <select required value={row.identity_ref} onChange={(event) => setRoles((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, identity_ref: event.target.value } : item))}>
                        <option value="">Choose identity…</option>
                        {identityOptions.map((identity) => <option key={identity} value={identity}>{identity}</option>)}
                      </select>
                    </label>
                    <label><span className="sr-only">{`Capability for ${row.action}`}</span>
                      <select required value={row.capability_ref} onChange={(event) => setRoles((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, capability_ref: event.target.value } : item))}>
                        <option value="">Choose capability…</option>
                        {capabilityOptions.map((capability) => <option key={capability} value={capability}>{capability}</option>)}
                      </select>
                    </label>
                  </div>
                ))}
                <label><span>Approval assertion supplied with the consequential step</span>
                  <select required value={approvalMode} onChange={(event) => setApprovalMode(event.target.value)} data-testid="policy-approval-mode">
                    <option value="">Decide…</option>
                    <option value="missing">None (watch it fail closed)</option>
                    <option value="valid">Valid human approval</option>
                    <option value="expired">Expired approval</option>
                  </select>
                </label>
                {/* The three protection requirements are learner decisions, not
                    academy constants. Each starts undecided; the design review
                    will show — with real checks — what disabling one costs. */}
                {POLICY_QUESTIONS.map((question) => (
                  <label key={question.key}><span>{question.label}</span>
                    <select
                      required
                      value={policyChoices[question.key]}
                      onChange={(event) => setPolicyChoices((current) => ({ ...current, [question.key]: event.target.value as PolicyAnswer }))}
                      data-testid={`policy-${question.key}`}
                    >
                      <option value="">Decide…</option>
                      <option value="yes">Yes — require it</option>
                      <option value="no">No — proceed without it</option>
                    </select>
                  </label>
                ))}
                {independent ? (
                  <>
                    {scenario.declared_zones.length ? (
                      <div className="design-zone-row">
                        <label><span>Source zone</span><select required value={sourceZone} onChange={(event) => setSourceZone(event.target.value)} data-testid="zone-source"><option value="">Decide…</option>{scenario.declared_zones.map((zone) => <option key={zone} value={zone}>{zone}</option>)}</select></label>
                        <label><span>Target zone</span><select required value={targetZone} onChange={(event) => setTargetZone(event.target.value)} data-testid="zone-target"><option value="">Decide…</option>{scenario.declared_zones.map((zone) => <option key={zone} value={zone}>{zone}</option>)}</select></label>
                      </div>
                    ) : null}
                    {/* Choosing a ref is the decision to require it; "None" is
                        the decision to design without one. Neither is assumed. */}
                    <label><span>Declared delegation</span><select required value={delegationId} onChange={(event) => setDelegationId(event.target.value)} data-testid="coordination-delegation"><option value="">Decide…</option><option value={NONE_REF}>None — this design declares no delegation</option>{scenario.declared_delegations.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
                    <label><span>Declared handoff</span><select required value={handoffId} onChange={(event) => setHandoffId(event.target.value)} data-testid="coordination-handoff"><option value="">Decide…</option><option value={NONE_REF}>None — this design declares no handoff</option>{scenario.declared_handoffs.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
                    <label><span>Your assurance claim (scoped to this design)</span><textarea rows={3} value={claim} onChange={(event) => setClaim(event.target.value)} placeholder="What exactly does this run support, on which named surface?" /></label>
                    <label><span>Residual risk you accept</span><textarea rows={2} value={residualRisk} onChange={(event) => setResidualRisk(event.target.value)} placeholder="What remains possible — bypass, authentication, egress?" /></label>
                    <label><span>Falsification condition</span><textarea rows={2} value={falsification} onChange={(event) => setFalsification(event.target.value)} placeholder="What observation would prove your claim false?" /></label>
                  </>
                ) : null}
              </fieldset>
            ) : null}

            <button className="button button-accent button-large" type="submit" disabled={run.loading || !canRun}>{run.loading ? "Running capstone…" : "Run capstone workflow"}</button>
            {!canRun ? <p className="muted" role="status">Complete every allocation and decide all four policy questions{independent ? `, the delegation and handoff choices, ${zonesApplicable ? "the source and target zones, " : ""}and write the three assurance statements (at least 20 characters each)` : ""} before running.</p> : null}
          </form>
        </section>
      </> : null}
      {run.error ? <ErrorNotice title="Capstone run unavailable" message={`${run.error} No pass, failure, or assurance outcome has been fabricated.`} /> : null}
      {run.data ? <section className="lab-result"><div className="result-banner"><div><p className="eyebrow">Capstone execution</p><h2>{run.data.title}</h2></div><StatusBadge status={run.data.status} /></div><ContentBlocks blocks={run.data.blocks} />{run.data.diagnostics.length ? <Findings findings={run.data.diagnostics} /> : null}<InfoNotice title={run.data.completion_eligible ? "Execution requirement satisfied" : "Completion not yet supported"} tone={run.data.completion_eligible ? "success" : "warning"}><p>{run.data.safety_boundary}</p></InfoNotice></section> : null}
      {definition.data ? <AssessmentPanel assessmentId={definition.data.assessment_id} onComplete={async () => refreshProgress()} /> : null}
    </div>
  );
}
