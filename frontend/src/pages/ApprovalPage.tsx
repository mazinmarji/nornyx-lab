import { useState } from "react";
import { academyApi } from "../api/client";
import { ClaimCard } from "../components/ClaimCard";
import { CounterCard } from "../components/CounterCard";
import { DecisionCard } from "../components/DecisionCard";
import { ScenarioFlowDiagram } from "../components/Diagrams";
import { ErrorNotice, InfoNotice } from "../components/Feedback";
import { TraceTimeline } from "../components/TraceTimeline";
import { useAsyncTask } from "../components/useAsyncTask";
import { useAcademy } from "../context/AcademyContext";
import type { DemoOptions, ScenarioRun } from "../types";
import { defaultDemoOptions } from "./DemoPage";

export function ApprovalPage() {
  const [approvalState, setApprovalState] = useState<DemoOptions["approval_state"]>("missing");
  const [revision, setRevision] = useState("");
  const task = useAsyncTask<ScenarioRun>();
  const { setLastRun } = useAcademy();
  const [executedConfiguration, setExecutedConfiguration] = useState<{ runId: string; approvalState: DemoOptions["approval_state"]; revision: string | null } | null>(null);
  const governed = task.data?.variants.find((variant) => variant.id === "governed");
  const capabilityDecision = governed?.decisions.find((decision) => !decision.source_zone && !decision.target_zone);
  const crossingDecision = governed?.decisions.find((decision) => decision.source_zone || decision.target_zone);
  async function simulate() {
    const configurationSnapshot = { approvalState, revision: revision || null };
    setExecutedConfiguration(null);
    const result = await task.run(() => academyApi.runDemo({ ...defaultDemoOptions, approval_state: configurationSnapshot.approvalState, observed_subject_revision: configurationSnapshot.revision }));
    if (result) {
      setExecutedConfiguration({ runId: result.run_id, ...configurationSnapshot });
      setLastRun(result);
      requestAnimationFrame(() => document.getElementById("approval-result")?.focus());
    }
  }
  return (
    <div className="page">
      <header className="page-header"><p className="eyebrow">Assertion · freshness · subject binding · human authority</p><h1>Approval simulator</h1><p>See how a supplied approval state enters the same policy and enforcement path. An approval is not merely a “yes” string.</p></header>
      <section className="approval-simulator">
        <div className="approval-form"><h2>Approval assertion</h2><label><span>Assertion state</span><select value={approvalState} onChange={(event) => setApprovalState(event.target.value as DemoOptions["approval_state"])}><option value="missing">Missing</option><option value="valid">Valid human approval</option><option value="expired">Expired</option><option value="non_human">Non-human approver</option><option value="wrong_revision">Bound to wrong revision</option></select></label><label><span>Observed subject revision</span><input value={revision} onChange={(event) => setRevision(event.target.value)} placeholder="Leave blank for contract default" /></label><button className="button button-primary" type="button" disabled={task.loading} onClick={() => void simulate()}>{task.loading ? "Evaluating…" : "Evaluate approval path"}</button></div>
        <div className="approval-principles"><p className="eyebrow">Validation questions</p><ol><li>Was the approver authorized and human where required?</li><li>Was the assertion still fresh?</li><li>Was it bound to this exact subject revision?</li><li>Did a gate require it for this zone crossing?</li><li>Did an enforcement point apply the decision?</li></ol></div>
      </section>
      {task.error ? <ErrorNotice title="Approval simulation failed" message={`${task.error} No result was substituted.`} /> : null}
      {governed ? <section className="approval-result" id="approval-result" tabIndex={-1}>
        <section className="approval-provenance" aria-labelledby="approval-provenance-heading">
          <div><p className="eyebrow">Execution provenance</p><h2 id="approval-provenance-heading">Evaluated assertion snapshot</h2></div>
          <dl><div><dt>Occurrence</dt><dd>{task.data?.run_id}</dd></div><div><dt>Assertion state</dt><dd>{executedConfiguration?.runId === task.data?.run_id ? executedConfiguration.approvalState.replaceAll("_", " ") : "Unavailable"}</dd></div><div><dt>Observed revision</dt><dd>{executedConfiguration?.runId === task.data?.run_id ? executedConfiguration.revision ?? "Contract revision" : "Unavailable"}</dd></div></dl>
        </section>
        <ScenarioFlowDiagram decision={crossingDecision ?? capabilityDecision} />
        <section className="decision-outcomes" aria-labelledby="approval-decision-outcomes">
          <p className="eyebrow">Policy result sequence</p><h2 id="approval-decision-outcomes">Capability and zone-crossing decisions</h2>
          <div className="decision-outcome-grid" role="list">
            {capabilityDecision ? <article role="listitem" data-testid="approval-capability-decision"><span>Capability decision</span><strong>{capabilityDecision.code}</strong><small>{capabilityDecision.effect.replaceAll("_", " ")}</small></article> : null}
            {crossingDecision ? <article role="listitem" data-testid="approval-crossing-decision"><span>Zone-crossing decision</span><strong>{crossingDecision.code}</strong><small>{crossingDecision.effect.replaceAll("_", " ")}</small></article> : null}
          </div>
          {!capabilityDecision || !crossingDecision ? <InfoNotice title="Decision sequence incomplete" tone="warning"><p>The response did not include both the capability and zone-crossing evaluations, so the approval path is only partially inspectable.</p></InfoNotice> : null}
        </section>
        {governed.decisions.map((decision, index) => <DecisionCard decision={decision} index={index} key={`${decision.code}-${index}`} />)}<div className="counter-grid">{governed.counters.map((counter, index) => <CounterCard counter={counter} key={`${counter.action}-${index}`} />)}</div><TraceTimeline trace={governed.trace} title="Approval decision trace" /><div className="claim-stack">{governed.claims.map((claim, index) => <ClaimCard claim={claim} key={`${claim.claim}-${index}`} />)}</div></section> : <InfoNotice title="Run the simulator to inspect a real response"><p>{task.loading ? "The prior result is hidden while the selected assertion is evaluated." : "Decision details, counters, and trace events will be rendered only after the API evaluates the selected state."}</p></InfoNotice>}
    </div>
  );
}
