import { useState } from "react";
import { academyApi } from "../api/client";
import { ClaimCard } from "../components/ClaimCard";
import { CounterCard } from "../components/CounterCard";
import { EvidencePanel } from "../components/EvidencePanel";
import { ErrorNotice, InfoNotice } from "../components/Feedback";
import { DemoConfigurationSnapshot } from "../components/ScenarioResults";
import { TraceTimeline } from "../components/TraceTimeline";
import { useAsyncTask } from "../components/useAsyncTask";
import { useAcademy } from "../context/AcademyContext";
import type { ScenarioRun } from "../types";
import { defaultDemoOptions } from "./DemoPage";

export function EvidencePage() {
  const { lastRun, setLastRun } = useAcademy();
  const task = useAsyncTask<ScenarioRun>();
  const [variantId, setVariantId] = useState<"ungoverned" | "governed">("governed");
  const [requestStarted, setRequestStarted] = useState(false);
  const [executedConfiguration, setExecutedConfiguration] = useState<{ runId: string; options: typeof defaultDemoOptions } | null>(null);
  const priorRun = !requestStarted && !task.loading && !task.error ? lastRun : null;
  const run = task.data ?? priorRun;
  const variant = run?.variants.find((item) => item.id === variantId);
  async function requestEvidence() {
    const configurationSnapshot = { ...defaultDemoOptions };
    setRequestStarted(true);
    setExecutedConfiguration(null);
    const response = await task.run(() => academyApi.runDemo(configurationSnapshot));
    if (response) {
      setExecutedConfiguration({ runId: response.run_id, options: configurationSnapshot });
      setLastRun(response);
    }
  }
  return (
    <div className="page">
      <header className="page-header tool-header"><div><p className="eyebrow">Events · bindings · counters · findings · claim scope</p><h1>Evidence explorer</h1><p>Follow an occurrence from plan through decision and tool observation, then test what its evidence can and cannot support.</p></div>{run ? <button className="button button-secondary" type="button" disabled={task.loading} onClick={() => void requestEvidence()}>Run fresh scenario</button> : null}</header>
      {!run ? <section className="evidence-empty" aria-live="polite"><div><h2>{task.loading ? "Requesting fresh evidence" : "No scenario evidence loaded"}</h2><p>{task.loading ? "Previously loaded evidence is hidden until this request completes and can be bound to its own occurrence." : "Request a fresh structured run from the service. The explorer does not ship with a fabricated evidence package."}</p><button className="button button-primary" type="button" disabled={task.loading} onClick={() => void requestEvidence()}>{task.loading ? "Running scenario…" : "Run demo and load evidence"}</button></div></section> : null}
      {task.error ? <ErrorNotice title="Evidence request failed" message={`${task.error} No evidence has been inferred.`} /> : null}
      {run ? <>
        <section className="evidence-runbar"><div><span>Occurrence</span><strong>{run.run_id}</strong></div><div><span>Scenario</span><strong>{run.scenario_id}</strong></div><div><span>Planner</span><strong>{run.deterministic ? "Deterministic" : "Live"}</strong></div><div><span>Run source</span><strong>{task.data ? "Fresh request" : "Previously loaded"}</strong></div></section>
        <DemoConfigurationSnapshot configuration={executedConfiguration?.runId === run.run_id ? executedConfiguration.options : null} source={task.data ? "Captured with this evidence request" : "Previously loaded academy run"} />
        <div className="segmented-control" role="group" aria-label="Evidence variant"><button type="button" aria-pressed={variantId === "ungoverned"} onClick={() => setVariantId("ungoverned")}>Without governance</button><button type="button" aria-pressed={variantId === "governed"} onClick={() => setVariantId("governed")}>With controls</button></div>
        {variant ? <div className="evidence-layout"><div><div className="counter-grid">{variant.counters.map((counter, index) => <CounterCard counter={counter} key={`${counter.action}-${index}`} />)}</div><TraceTimeline trace={variant.trace} /></div><aside><EvidencePanel evidence={variant.evidence} /></aside></div> : null}
        {variant ? <section className="claims-section"><div className="section-heading"><div><p className="eyebrow">Assurance interpretation</p><h2>What can we honestly claim?</h2></div></div><div className="claim-stack">{variant.claims.map((claim, index) => <ClaimCard claim={claim} key={`${claim.claim}-${index}`} />)}</div><InfoNotice title="Evidence integrity is not evidence completeness" tone="warning"><p>A digest or lock can show that supplied bytes match a binding. It does not establish that every relevant path emitted an event, or that an event’s assertion is true.</p></InfoNotice></section> : null}
      </> : null}
    </div>
  );
}
