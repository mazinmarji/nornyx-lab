import { useState } from "react";
import { academyApi } from "../api/client";
import { ErrorNotice, InfoNotice } from "../components/Feedback";
import { ScenarioResults } from "../components/ScenarioResults";
import { useAsyncTask } from "../components/useAsyncTask";
import { useAcademy } from "../context/AcademyContext";
import type { DemoOptions, ScenarioRun } from "../types";
import { defaultDemoOptions } from "./DemoPage";

const experiments: { label: string; description: string; patch: Partial<DemoOptions> }[] = [
  { label: "Expire the approval", description: "Supply an expired human approval assertion.", patch: { approval_state: "expired" } },
  { label: "Change contract revision", description: "Bind the observation to a mismatched revision.", patch: { approval_state: "wrong_revision", observed_subject_revision: "sha256:stale-revision" } },
  { label: "Disable enforcement point", description: "Leave declarations present but remove this cooperative interception.", patch: { enforcement_enabled: false } },
  { label: "Fail open", description: "Make the enforcement surface fail and allow the path onward.", patch: { enforcement_failure: true, failure_mode: "fail_open" } },
  { label: "Fail closed", description: "Make the same surface fail closed.", patch: { enforcement_failure: true, failure_mode: "fail_closed" } },
  { label: "Remove injection", description: "Use trusted task context without the hostile instruction.", patch: { injection_enabled: false } },
];

export function WorkbenchPage() {
  const [options, setOptions] = useState<DemoOptions>(defaultDemoOptions);
  const task = useAsyncTask<ScenarioRun>();
  const { setLastRun, refreshProgress } = useAcademy();
  async function run() {
    const response = await task.run(() => academyApi.runDemo(options));
    if (response) { setLastRun(response); await refreshProgress().catch(() => undefined); }
  }
  return (
    <div className="page">
      <header className="page-header"><p className="eyebrow">Controlled failure laboratory</p><h1>Scenario workbench</h1><p>Change a boundary, run both variants, inspect the evidence, and let each isolated experiment restore itself.</p></header>
      <section className="experiment-grid" aria-label="Preset experiments">
        {experiments.map((experiment) => <button type="button" key={experiment.label} onClick={() => setOptions({ ...defaultDemoOptions, ...experiment.patch })} className={Object.entries(experiment.patch).every(([key, value]) => options[key as keyof DemoOptions] === value) ? "selected" : ""}><strong>{experiment.label}</strong><span>{experiment.description}</span></button>)}
      </section>
      <section className="workbench-controls">
        <div><p className="eyebrow">Active configuration</p><h2>Authorization and failure inputs</h2></div>
        <div className="form-grid">
          <label className="toggle-field"><input type="checkbox" checked={options.injection_enabled} onChange={(event) => setOptions({ ...options, injection_enabled: event.target.checked })} /><span><strong>Prompt injection</strong><small>Untrusted content proposes publication.</small></span></label>
          <label className="toggle-field"><input type="checkbox" checked={options.enforcement_enabled} onChange={(event) => setOptions({ ...options, enforcement_enabled: event.target.checked })} /><span><strong>Enforcement enabled</strong><small>Cooperative named surface intercepts the tool.</small></span></label>
          <label className="toggle-field"><input type="checkbox" checked={options.enforcement_failure} onChange={(event) => setOptions({ ...options, enforcement_failure: event.target.checked })} /><span><strong>Enforcement failure</strong><small>Exercise its declared failure behavior.</small></span></label>
          <label><span>Failure mode</span><select value={options.failure_mode} onChange={(event) => setOptions({ ...options, failure_mode: event.target.value as DemoOptions["failure_mode"] })}><option value="fail_closed">Fail closed — a broken check blocks the action</option><option value="fail_open">Fail open — a broken check lets the action through</option><option value="bounded">Bounded — an application-defined fallback blocks the irreversible action</option></select><small>What the application does when its authorization check cannot run. None of these fallbacks is a Nornyx decision.</small></label>
          <label><span>Approval</span><select value={options.approval_state} onChange={(event) => setOptions({ ...options, approval_state: event.target.value as DemoOptions["approval_state"] })}><option value="missing">Missing</option><option value="valid">Valid</option><option value="expired">Expired</option><option value="non_human">Non-human</option><option value="wrong_revision">Wrong revision</option></select></label>
          <label><span>Observed revision</span><input value={options.observed_subject_revision ?? ""} onChange={(event) => setOptions({ ...options, observed_subject_revision: event.target.value || null })} placeholder="Contract revision or blank" /></label>
        </div>
        <div className="button-row"><button className="button button-accent button-large" type="button" disabled={task.loading} onClick={() => void run()}>{task.loading ? "Running isolated experiment…" : "Run both variants"}</button><button className="button button-secondary" type="button" onClick={() => setOptions(defaultDemoOptions)}>Restore scenario</button></div>
      </section>
      <InfoNotice title="Restoration is part of the result"><p>The response’s <code>restored</code> field is displayed after execution. The UI does not assume cleanup succeeded.</p></InfoNotice>
      {task.error ? <ErrorNotice title="Experiment failed" message={`${task.error} No governance result has been inferred.`} onRetry={() => void run()} /> : null}
      {task.data ? <ScenarioResults run={task.data} /> : null}
    </div>
  );
}

