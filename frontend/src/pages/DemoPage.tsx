import { useMemo, useState } from "react";
import { academyApi } from "../api/client";
import { AssessmentPanel } from "../components/AssessmentPanel";
import { ErrorNotice, InfoNotice } from "../components/Feedback";
import { ScenarioResults } from "../components/ScenarioResults";
import { useAsyncTask } from "../components/useAsyncTask";
import { useAcademy } from "../context/AcademyContext";
import type { DemoOptions, ScenarioRun } from "../types";

export const defaultDemoOptions: DemoOptions = {
  injection_enabled: true,
  enforcement_enabled: true,
  enforcement_failure: false,
  failure_mode: "fail_closed",
  identity_ref: "identity.research_assistant",
  observed_subject_revision: null,
  approval_state: "missing",
  planner_mode: "deterministic",
};

export function DemoPage() {
  const { catalog, lastRun, setLastRun, refreshProgress } = useAcademy();
  const task = useAsyncTask<ScenarioRun>();
  const [options, setOptions] = useState<DemoOptions>(defaultDemoOptions);
  const [showControls, setShowControls] = useState(false);
  const [requestStarted, setRequestStarted] = useState(false);
  const [executedConfiguration, setExecutedConfiguration] = useState<{ runId: string; options: DemoOptions } | null>(null);
  const priorRun = !requestStarted && !task.loading && !task.error ? lastRun : null;
  const result = task.data ?? priorRun;
  const assessmentId = useMemo(() => {
    if (!catalog || !result) return null;
    return catalog.modules.find((module) => module.scenario_id === result.scenario_id)?.completion.assessment_id ?? null;
  }, [catalog, result]);

  function update<K extends keyof DemoOptions>(key: K, value: DemoOptions[K]) {
    setOptions((current) => ({ ...current, [key]: value }));
  }

  async function runBoth() {
    const configurationSnapshot = { ...options };
    setRequestStarted(true);
    setExecutedConfiguration(null);
    const run = await task.run(() => academyApi.runDemo(configurationSnapshot));
    if (run) {
      setExecutedConfiguration({ runId: run.run_id, options: configurationSnapshot });
      setLastRun(run);
      await refreshProgress().catch(() => undefined);
      requestAnimationFrame(() => document.getElementById("demo-results")?.focus());
    }
  }

  return (
    <div className="page demo-page">
      <header className="page-header demo-header">
        <div>
          <p className="eyebrow">Five-minute guided demonstration</p>
          <h1>One plan. Two control paths.<br />A measurable difference.</h1>
          <p>An AI research agent reads an untrusted webpage that tells it to publish sensitive content. Run both variants from the real training engine and follow the action to the inert tool ledger.</p>
        </div>
        <ol className="demo-steps" aria-label="Demonstration steps">
          <li className="active"><span>1</span>Understand the plan</li>
          <li><span>2</span>Run both paths</li>
          <li><span>3</span>Inspect counters</li>
          <li><span>4</span>Read evidence</li>
          <li><span>5</span>Check your reasoning</li>
        </ol>
      </header>

      <section className="demo-primer">
        <div className="primer-copy"><p className="eyebrow">Why this matters</p><h2>The dangerous transition is from words to authority.</h2><p>An assistant can draft a publication. An agent with a publishing tool can attempt it. A refusal sentence does not settle whether the tool ran; observed attempts and completions do.</p></div>
        <div className="counter-key" aria-label="How to interpret side effect counters"><div><strong>0 / 0</strong><span>Prevented before execution, if the action was planned and evidence is complete</span></div><div><strong>1 / 0</strong><span>Tool attempt began but did not complete</span></div><div><strong>1 / 1</strong><span>Tool action completed</span></div><div><strong>? / ?</strong><span>Evidence cannot support a conclusion</span></div></div>
      </section>

      <section className="run-console" aria-labelledby="run-demo-heading">
        <div className="run-console-main">
          <p className="eyebrow">Safe deterministic scenario</p>
          <h2 id="run-demo-heading">Run the ungoverned and governed paths together</h2>
          <p>Both variants receive the same planner input and proposed plan. Business effects are recorded in an inert in-memory ledger; nothing is published externally.</p>
          <div className="button-row">
            <button className="button button-accent button-large" type="button" disabled={task.loading} onClick={() => void runBoth()}>
              {task.loading ? <><span className="button-spinner" aria-hidden="true" /> Running both paths…</> : "Run both paths"}
            </button>
            <button className="button button-dark-secondary" type="button" aria-expanded={showControls} aria-controls="failure-controls" onClick={() => setShowControls((value) => !value)}>{showControls ? "Hide" : "Introduce"} a controlled failure</button>
          </div>
        </div>
        <div className="run-boundary"><span aria-hidden="true">□</span><div><strong>No external side effects</strong><p>Default plans are deterministic and training tools are inert.</p></div></div>
      </section>

      {showControls ? (
        <section id="failure-controls" className="control-panel" aria-labelledby="failure-controls-heading">
          <div className="section-heading"><div><p className="eyebrow">Guided experimentation</p><h2 id="failure-controls-heading">Change one boundary, then run again</h2></div><button type="button" className="text-button" onClick={() => setOptions(defaultDemoOptions)}>Restore recommended defaults</button></div>
          <div className="form-grid">
            <label className="toggle-field"><input type="checkbox" checked={options.injection_enabled} onChange={(event) => update("injection_enabled", event.target.checked)} /><span><strong>Introduce prompt injection</strong><small>The untrusted page asks the agent to publish.</small></span></label>
            <label className="toggle-field"><input type="checkbox" checked={options.enforcement_enabled} onChange={(event) => update("enforcement_enabled", event.target.checked)} /><span><strong>Enable enforcement point</strong><small>Control the named cooperative tool path.</small></span></label>
            <label className="toggle-field"><input type="checkbox" checked={options.enforcement_failure} onChange={(event) => update("enforcement_failure", event.target.checked)} /><span><strong>Make enforcement fail</strong><small>Observe fail-open, fail-closed, or bounded behavior.</small></span></label>
            <label><span>Failure mode</span><select value={options.failure_mode} onChange={(event) => update("failure_mode", event.target.value as DemoOptions["failure_mode"])}><option value="fail_closed">Fail closed</option><option value="fail_open">Fail open</option><option value="bounded">Bounded fallback</option></select></label>
            <label><span>Approval assertion</span><select value={options.approval_state} onChange={(event) => update("approval_state", event.target.value as DemoOptions["approval_state"])}><option value="missing">Missing</option><option value="valid">Valid</option><option value="expired">Expired</option><option value="non_human">Non-human approver</option><option value="wrong_revision">Wrong contract revision</option></select></label>
            <label><span>Agent identity</span><input value={options.identity_ref} onChange={(event) => update("identity_ref", event.target.value)} /></label>
            <label><span>Observed subject revision</span><input value={options.observed_subject_revision ?? ""} placeholder="Use contract revision" onChange={(event) => update("observed_subject_revision", event.target.value || null)} /></label>
            <label><span>Planner mode</span><select value={options.planner_mode} onChange={(event) => update("planner_mode", event.target.value as DemoOptions["planner_mode"])}><option value="deterministic">Deterministic fixture (offline)</option><option value="live">Configured live model</option></select></label>
          </div>
          <InfoNotice title="The experiment is isolated" tone="info"><p>Each run receives fresh state. The response confirms whether restoration completed; a failure never silently becomes a success.</p></InfoNotice>
        </section>
      ) : null}

      {task.error ? <ErrorNotice title="The demonstration did not run" message={`${task.error} No scenario outcome has been substituted.`} onRetry={() => void runBoth()} /> : null}
      {result ? <div id="demo-results" tabIndex={-1}><ScenarioResults run={result} executedConfiguration={executedConfiguration?.runId === result.run_id ? executedConfiguration.options : null} configurationSource={task.data ? "Captured with this request" : "Previously loaded academy run"} /></div> : (
        <section className="awaiting-run" aria-live="polite"><span aria-hidden="true">▶</span><div><h2>{task.loading ? "Running a fresh scenario" : "Results will appear here"}</h2><p>{task.loading ? "Prior results are hidden while the service evaluates the captured configuration." : "Use “Run both paths” to request a structured scenario result from the local academy service."}</p></div></section>
      )}
      {result && assessmentId ? <AssessmentPanel assessmentId={assessmentId} onComplete={async () => refreshProgress()} /> : result ? <InfoNotice title="Assessment mapping unavailable" tone="warning"><p>The catalog did not map this API scenario to an assessment. The run remains inspectable, but completion cannot be awarded from a click-through.</p></InfoNotice> : null}
    </div>
  );
}
