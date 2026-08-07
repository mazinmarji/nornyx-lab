import { useEffect, useState } from "react";
import { academyApi } from "../api/client";
import { AssessmentPanel } from "../components/AssessmentPanel";
import { ContentBlocks, Findings } from "../components/ContentBlocks";
import { ErrorNotice, InfoNotice, LoadingState } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useAsyncTask } from "../components/useAsyncTask";
import { useAcademy } from "../context/AcademyContext";
import type { CapstoneDefinition, StructuredLabRun } from "../types";

export function CapstonePage() {
  const definition = useAsyncTask<CapstoneDefinition>();
  const run = useAsyncTask<StructuredLabRun>();
  const { refreshProgress } = useAcademy();
  const [framework, setFramework] = useState("framework-neutral");
  const [failure, setFailure] = useState("prompt-injection");
  const [scaffolding, setScaffolding] = useState("guided");
  useEffect(() => { void definition.run(() => academyApi.capstone()); }, []); // stable task
  async function runCapstone() {
    const result = await run.run(() => academyApi.runCapstone({ framework, failure_injection: failure, scaffolding }));
    if (result) await refreshProgress().catch(() => undefined);
  }
  const title = typeof definition.data?.title === "string" ? definition.data.title : "Govern a multi-agent delivery workflow";
  const summary = typeof definition.data?.summary === "string" ? definition.data.summary : null;
  const guidance = Array.isArray(definition.data?.guidance) ? definition.data.guidance.filter((item): item is string => typeof item === "string") : [];
  const requirements = Array.isArray(definition.data?.requirements) ? definition.data.requirements.filter((item): item is string => typeof item === "string") : [];
  return (
    <div className="page capstone-page">
      <header className="page-header capstone-header"><div><p className="eyebrow">Capstone workspace</p><h1>{title}</h1><p>{summary ?? "Configure, execute, and assess a realistic multi-agent workflow through the connected academy service."}</p></div>{definition.data?.status ? <StatusBadge status={definition.data.status} /> : null}</header>
      {definition.loading ? <LoadingState label="Loading capstone definition…" /> : null}
      {definition.error ? <ErrorNotice title="Capstone API unavailable" message={`${definition.error} The workspace will not substitute a mock capstone.`} onRetry={() => void definition.run(() => academyApi.capstone())} /> : null}
      {definition.data ? <>
        <section className="capstone-map" aria-label="Capstone control map"><article><span>01</span><h2>Separate identities</h2><p>Builder, reviewer, release agent, and approver carry distinct capabilities.</p></article><article><span>02</span><h2>Cross boundaries</h2><p>Trusted source and untrusted input move through explicit trust zones and handoffs.</p></article><article><span>03</span><h2>Enforce gates</h2><p>Approval, separation of duties, integrity, and runtime binding control tool paths.</p></article><article><span>04</span><h2>Defend a claim</h2><p>Evidence supports a scoped assurance statement with residual risk.</p></article></section>
        <section className="capstone-layout">
          <div className="capstone-brief"><p className="eyebrow">Service-provided brief</p><h2>Requirements</h2>{requirements.length ? <ul>{requirements.map((item) => <li key={item}>{item}</li>)}</ul> : <p>The service did not enumerate requirement text.</p>}{guidance.length ? <details open={scaffolding === "guided"}><summary>Beginner guidance</summary><ol>{guidance.map((item) => <li key={item}>{item}</li>)}</ol></details> : null}</div>
          <form className="capstone-config" onSubmit={(event) => { event.preventDefault(); void runCapstone(); }}><p className="eyebrow">Execution configuration</p><h2>Configure the run</h2><label><span>Framework surface</span><select value={framework} onChange={(event) => setFramework(event.target.value)}>{definition.data.frameworks.map((item) => <option value={item} key={item}>{item === "framework-neutral" ? "Framework-neutral" : `${item === "crewai" ? "CrewAI" : "LangGraph"} adapter`}</option>)}</select></label><label><span>Controlled failure</span><select value={failure} onChange={(event) => setFailure(event.target.value)}>{definition.data.failure_injections.map((item) => <option value={item} key={item}>{item.replaceAll("-", " ")}</option>)}</select></label><label><span>Guidance</span><select value={scaffolding} onChange={(event) => setScaffolding(event.target.value)}><option value="guided">Guided</option><option value="reduced">Reduced scaffolding</option><option value="independent">Independent review</option></select></label><button className="button button-accent button-large" type="submit" disabled={run.loading}>{run.loading ? "Running capstone…" : "Run capstone workflow"}</button></form>
        </section>
      </> : null}
      {run.error ? <ErrorNotice title="Capstone run unavailable" message={`${run.error} No pass, failure, or assurance outcome has been fabricated.`} /> : null}
      {run.data ? <section className="lab-result"><div className="result-banner"><div><p className="eyebrow">Capstone execution</p><h2>{run.data.title}</h2></div><StatusBadge status={run.data.status} /></div><ContentBlocks blocks={run.data.blocks} />{run.data.diagnostics.length ? <Findings findings={run.data.diagnostics} /> : null}<InfoNotice title={run.data.completion_eligible ? "Execution requirement satisfied" : "Completion not yet supported"} tone={run.data.completion_eligible ? "success" : "warning"}><p>{run.data.safety_boundary}</p></InfoNotice></section> : null}
      {definition.data ? <AssessmentPanel assessmentId={definition.data.assessment_id} onComplete={async () => refreshProgress()} /> : null}
    </div>
  );
}
