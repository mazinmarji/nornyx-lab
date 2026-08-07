import { useEffect, useState, type FormEvent } from "react";
import { academyApi } from "../api/client";
import { ErrorNotice, InfoNotice } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useAsyncTask } from "../components/useAsyncTask";
import type { LiveModelSettingsResponse } from "../types";

export function SettingsPage() {
  const [enabled, setEnabled] = useState(false);
  const [model, setModel] = useState("claude-sonnet-4-20250514");
  const [apiKey, setApiKey] = useState("");
  const task = useAsyncTask<LiveModelSettingsResponse>();
  useEffect(() => {
    void task.run(() => academyApi.liveSettings()).then((settings) => {
      if (settings) { setEnabled(settings.enabled); setModel(settings.model); }
    });
  }, []); // stable task
  async function save(event: FormEvent) {
    event.preventDefault();
    const result = await task.run(() => academyApi.saveLiveSettings({ enabled, provider: "anthropic", model, api_key: apiKey || null }));
    if (result) setApiKey("");
  }
  return (
    <div className="page settings-page">
      <header className="page-header"><p className="eyebrow">Offline first · explicit live opt-in</p><h1>Settings</h1><p>The deterministic planner works without a key or network. Live mode can propose a different plan; it cannot silently replace a Nornyx authorization decision for the same request.</p></header>
      <section className="settings-layout">
        <form className="settings-card" onSubmit={(event) => void save(event)}><div className="settings-card-heading"><div><p className="eyebrow">Optional</p><h2>Live-model planner</h2></div><label className="switch"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /><span aria-hidden="true" /><strong>{enabled ? "Enabled" : "Disabled"}</strong></label></div><p>Use a live model only to propose the scenario plan. Every proposed action is displayed before its governed and ungoverned paths are interpreted.</p><label><span>Provider</span><input value="Anthropic" disabled /></label><label><span>Model</span><input value={model} onChange={(event) => setModel(event.target.value)} disabled={!enabled} /></label><label><span>API key</span><input type="password" autoComplete="off" value={apiKey} onChange={(event) => setApiKey(event.target.value)} disabled={!enabled} placeholder="Entered for this process only" /><small>The service must keep this in process memory, never the learner record or logs.</small></label><button className="button button-primary" type="submit" disabled={task.loading}>{task.loading ? "Saving…" : "Save live-model setting"}</button></form>
        <aside className="boundary-card"><p className="eyebrow">Invariant boundaries</p><h2>What live mode does not change</h2><ul><li>Nornyx remains the source of contract and decision semantics.</li><li>Default business actions remain inert training simulations.</li><li>A different plan can create a different whole-run outcome.</li><li>No API key is written to progress storage.</li><li>Live mode is visibly labeled in every result.</li></ul></aside>
      </section>
      {task.error ? <ErrorNotice title="Settings were not applied" message={task.error} /> : null}
      {task.data ? <section className="settings-response" aria-live="polite"><StatusBadge status={task.data.configured === task.data.enabled ? "pass" : "unknown"} /><div><h2>{task.data.enabled ? "Live planner enabled" : "Deterministic offline planner selected"}</h2><p>{task.data.boundary}</p><p><strong>Secret persisted:</strong> {task.data.persisted ? "Service reported yes — review configuration" : "No"}</p></div></section> : <InfoNotice title="Deterministic mode is the baseline"><p>No setup is required. Use live mode only when comparing planner behavior is part of the lesson.</p></InfoNotice>}
    </div>
  );
}
