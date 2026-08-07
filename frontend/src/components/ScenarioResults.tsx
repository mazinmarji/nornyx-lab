import type { DemoOptions, DecisionTrace, ScenarioRun, ScenarioVariant } from "../types";
import { ClaimCard } from "./ClaimCard";
import { CounterCard } from "./CounterCard";
import { DecisionCard } from "./DecisionCard";
import { EvidencePanel } from "./EvidencePanel";
import { InfoNotice } from "./Feedback";
import { ScenarioFlowDiagram } from "./Diagrams";
import { TraceTimeline } from "./TraceTimeline";
import { counterIsConsistent } from "./counterSemantics";

function yesNo(value: boolean): string {
  return value ? "Enabled" : "Disabled";
}

export function DemoConfigurationSnapshot({
  configuration,
  source,
}: {
  configuration?: DemoOptions | null;
  source: string;
}) {
  return (
    <section className="run-provenance" aria-labelledby="run-provenance-heading" data-testid="executed-configuration">
      <div className="run-provenance-heading">
        <div>
          <p className="eyebrow">Execution provenance</p>
          <h3 id="run-provenance-heading">Executed configuration</h3>
        </div>
        <span>{source}</span>
      </div>
      {configuration ? (
        <dl className="configuration-grid">
          <div><dt>Prompt injection</dt><dd>{yesNo(configuration.injection_enabled)}</dd></div>
          <div><dt>Enforcement</dt><dd>{yesNo(configuration.enforcement_enabled)}</dd></div>
          <div><dt>Enforcement failure</dt><dd>{yesNo(configuration.enforcement_failure)}</dd></div>
          <div><dt>Failure mode</dt><dd>{configuration.failure_mode.replaceAll("_", " ")}</dd></div>
          <div><dt>Approval assertion</dt><dd>{configuration.approval_state.replaceAll("_", " ")}</dd></div>
          <div><dt>Identity</dt><dd>{configuration.identity_ref}</dd></div>
          <div><dt>Observed revision</dt><dd>{configuration.observed_subject_revision ?? "Contract revision"}</dd></div>
          <div><dt>Planner</dt><dd>{configuration.planner_mode}</dd></div>
        </dl>
      ) : (
        <p className="provenance-unavailable">This is a previously loaded run. Its response remains inspectable, but this page did not execute it and cannot reconstruct the exact request configuration.</p>
      )}
    </section>
  );
}

function decisionScope(decision: DecisionTrace): string {
  if (!decision.requested) return "Governance path";
  if (decision.source_zone || decision.target_zone) return "Zone-crossing decision";
  return "Capability decision";
}

function counterSummary(counter: ScenarioVariant["counters"][number]): string {
  if (!counterIsConsistent(counter)) {
    return `Indeterminate (service reported ${counter.attempts ?? "?"} / ${counter.completions ?? "?"})`;
  }
  return `${counter.attempts ?? "?"} attempts / ${counter.completions ?? "?"} completions`;
}

function VariantPanel({ variant }: { variant: ScenarioVariant }) {
  const diagramDecision = variant.decisions.find((decision) => decision.source_zone || decision.target_zone) ?? variant.decisions[0];
  return (
    <article className={`variant-panel variant-${variant.id}`} data-testid={`variant-${variant.id}`}>
      <header className="variant-header">
        <div>
          <p className="eyebrow">{variant.id === "governed" ? "With Nornyx-derived controls" : "Without governance"}</p>
          <h2>{variant.title}</h2>
        </div>
        <span className={`variant-mode ${variant.governance_enabled ? "mode-governed" : "mode-ungoverned"}`}>
          {variant.governance_enabled ? "Governance enabled" : "No governance decision"}
        </span>
      </header>
      <ScenarioFlowDiagram decision={diagramDecision} />
      <div className="counter-grid">
        {variant.counters.map((counter, index) => (
          <div key={`${counter.action}-${index}`} data-testid={`${counter.action.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}-counter-${variant.id}`}>
            <CounterCard counter={counter} />
          </div>
        ))}
      </div>
      <section className="decision-outcomes" aria-labelledby={`decision-outcomes-${variant.id}`}>
        <p className="eyebrow">Policy result sequence</p>
        <h3 id={`decision-outcomes-${variant.id}`}>{variant.governance_enabled ? "Capability and zone-crossing decisions" : "Governance decision state"}</h3>
        {variant.decisions.length ? (
          <div className="decision-outcome-grid" role="list">
            {variant.decisions.map((decision, index) => (
              <article role="listitem" key={`${decision.code}-summary-${index}`} data-testid={`decision-outcome-${variant.id}-${index}`}>
                <span>{decisionScope(decision)}</span>
                <strong>{decision.code}</strong>
                <small>{decision.effect.replaceAll("_", " ")}</small>
              </article>
            ))}
          </div>
        ) : null}
      </section>
      <div className="decision-stack">
        {variant.decisions.length ? variant.decisions.map((decision, index) => (
          <DecisionCard key={`${decision.code}-${index}`} decision={decision} index={index} />
        )) : (
          <InfoNotice title="No decision was reported" tone="warning">
            <p>The service returned no authorization decision. The counters may describe a tool observation, but no policy conclusion is available.</p>
          </InfoNotice>
        )}
      </div>
      <details className="result-disclosure">
        <summary>Inspect ordered trace</summary>
        <TraceTimeline trace={variant.trace} title={`${variant.title} trace`} />
      </details>
      <details className="result-disclosure">
        <summary>Inspect evidence and validation findings</summary>
        <EvidencePanel evidence={variant.evidence} />
      </details>
      <section className="claims-section">
        <div className="section-heading compact-heading">
          <div><p className="eyebrow">Assurance interpretation</p><h3>What can this variant honestly claim?</h3></div>
        </div>
        <div className="claim-stack">
          {variant.claims.length ? variant.claims.map((claim, index) => <ClaimCard key={`${claim.claim}-${index}`} claim={claim} />) : <p className="muted">No claim interpretation was returned.</p>}
        </div>
      </section>
    </article>
  );
}

export function ScenarioResults({
  run,
  executedConfiguration,
  configurationSource = "Configuration snapshot unavailable",
}: {
  run: ScenarioRun;
  executedConfiguration?: DemoOptions | null;
  configurationSource?: string;
}) {
  const ungoverned = run.variants.find((variant) => variant.id === "ungoverned");
  const governed = run.variants.find((variant) => variant.id === "governed");
  const countersConsistent = run.variants.every((variant) => variant.counters.every(counterIsConsistent));
  return (
    <section className="scenario-results" aria-labelledby="scenario-result-heading">
      <div className="result-banner">
        <div>
          <p className="eyebrow">Run complete · {run.deterministic ? "deterministic fixture" : "live planner"}</p>
          <h2 id="scenario-result-heading">{run.title}</h2>
          <p>Run <code>{run.run_id}</code></p>
        </div>
        <span
          className={`restored-state ${run.restored ? "restored-confirmed" : "restored-warning"}`}
          data-testid="restoration-status"
          role={run.restored ? "status" : "alert"}
          aria-live={run.restored ? "polite" : "assertive"}
          aria-atomic="true"
        >
          {run.restored ? "Experiment restored" : "Warning: state restoration was not confirmed"}
        </span>
      </div>

      <DemoConfigurationSnapshot configuration={executedConfiguration} source={configurationSource} />

      <section className="plan-panel">
        <div className="section-heading">
          <div><p className="eyebrow">Same input · same proposed plan</p><h2>What the planner selected</h2></div>
          <span className={`taint-label taint-${run.planner_input.context_taint}`}>{run.planner_input.context_taint} context</span>
        </div>
        <dl className="field-list planner-fields">
          <div><dt>Task</dt><dd>{run.planner_input.task}</dd></div>
          <div><dt>Context origin</dt><dd>{run.planner_input.context_origin}</dd></div>
          <div><dt>Context authority</dt><dd>{run.planner_input.context_authority.replaceAll("_", " ")}</dd></div>
          <div><dt>Planner</dt><dd>{run.planner_input.planner_kind.replaceAll("_", " ")}{run.planner_input.model ? ` · ${run.planner_input.model}` : ""}</dd></div>
        </dl>
        <blockquote className="context-quote">{run.planner_input.context}</blockquote>
        <ol className="plan-steps">
          {run.plan.map((action) => (
            <li key={action.index}>
              <span>{action.index}</span>
              <div><h3>{action.action}</h3><p>{action.rationale}</p>{Object.keys(action.arguments).length ? <code>{JSON.stringify(action.arguments)}</code> : null}</div>
            </li>
          ))}
        </ol>
      </section>

      {run.comparison.length ? (
        <section className="comparison-summary" aria-labelledby="comparison-heading">
          <div className="section-heading"><div><p className="eyebrow">Counter proof</p><h2 id="comparison-heading">What changed at the tool boundary</h2></div></div>
          <div className="comparison-table-wrap">
            <table>
              <thead><tr><th scope="col">Action</th><th scope="col">Without governance</th><th scope="col">With controls</th><th scope="col">Interpretation</th></tr></thead>
              <tbody>{run.comparison.map((item, index) => {
                const comparisonConsistent = counterIsConsistent(item.ungoverned) && counterIsConsistent(item.governed);
                return <tr key={`${item.action}-${index}`}><th scope="row">{item.action}</th><td>{counterSummary(item.ungoverned)}</td><td>{counterSummary(item.governed)}</td><td>{comparisonConsistent ? item.interpretation : "Counter evidence is inconsistent; no comparison conclusion is supported."}</td></tr>;
              })}</tbody>
            </table>
          </div>
        </section>
      ) : null}

      {!countersConsistent ? <InfoNotice title="Counter evidence is inconsistent" tone="warning"><p>At least one reported meaning conflicts with its values. Counter cards and comparison claims are forced to an indeterminate state until the response is corrected.</p></InfoNotice> : null}

      <div className="variant-grid">
        {ungoverned ? <VariantPanel variant={ungoverned} /> : <InfoNotice title="Ungoverned result missing" tone="warning"><p>The service did not return the required ungoverned variant.</p></InfoNotice>}
        {governed ? <VariantPanel variant={governed} /> : <InfoNotice title="Governed result missing" tone="warning"><p>The service did not return the required governed variant.</p></InfoNotice>}
      </div>

      <section className="assurance-summary">
        <div>
          <p className="eyebrow">Strongest supported claim</p>
          <h2>{countersConsistent ? run.strongest_claim : "No counter-based conclusion is supported by this response."}</h2>
        </div>
        <div>
          <p className="eyebrow">Residual risk</p>
          <p>{run.residual_risk}</p>
        </div>
        <p className="safety-boundary"><strong>Training safety boundary:</strong> {run.safety_boundary}</p>
      </section>
    </section>
  );
}
