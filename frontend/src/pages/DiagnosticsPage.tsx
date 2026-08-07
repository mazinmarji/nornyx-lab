import { useEffect, useState } from "react";
import { academyApi } from "../api/client";
import { Findings } from "../components/ContentBlocks";
import { ErrorNotice, InfoNotice, LoadingState } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useAsyncTask } from "../components/useAsyncTask";
import type { ContractDetail, ContractValidation } from "../types";

export function DiagnosticsPage() {
  const [contractId, setContractId] = useState<"atlas" | "ledger">("atlas");
  const detail = useAsyncTask<ContractDetail>();
  const experiment = useAsyncTask<ContractValidation>();
  useEffect(() => { experiment.clear(); void detail.run(() => academyApi.contract(contractId)); }, [contractId]); // stable tasks
  async function changeRevision() {
    await experiment.run(() => academyApi.validateWorkbench(contractId, [{ operation: "set_subject_revision", target: "governance_evidence.subject_revision", value: `git:${"f".repeat(40)}` }]));
  }
  async function removeEvidenceField() {
    await experiment.run(() => academyApi.validateWorkbench(contractId, [{ operation: "remove_evidence_field", target: "approval_record", value: "content_hash" }]));
  }
  const active = experiment.data?.diagnostics ?? detail.data?.diagnostics ?? [];
  return (
    <div className="page">
      <header className="page-header"><p className="eyebrow">Exact codes · paths · missing fields · lock state</p><h1>Diagnostics viewer</h1><p>Read machine-returned findings without paraphrasing them into a stronger or different result.</p></header>
      <section className="diagnostic-toolbar"><label><span>Contract</span><select value={contractId} onChange={(event) => setContractId(event.target.value as "atlas" | "ledger")}><option value="atlas">Atlas</option><option value="ledger">Ledger</option></select></label><div className="button-row"><button className="button button-secondary" type="button" disabled={experiment.loading} onClick={() => void changeRevision()}>Mismatch evidence revision</button><button className="button button-secondary" type="button" disabled={experiment.loading} onClick={() => void removeEvidenceField()}>Remove evidence hash</button><button className="text-button" type="button" onClick={() => experiment.clear()}>Restore baseline</button></div></section>
      {detail.loading || experiment.loading ? <LoadingState label="Running exact validation…" /> : null}
      {detail.error || experiment.error ? <ErrorNotice message={detail.error ?? experiment.error ?? "Diagnostics unavailable"} /> : null}
      <section className="diagnostic-summary"><div><span>Source</span><strong>{experiment.data ? "Controlled workbench mutation" : "Authoritative contract"}</strong></div><div><span>Valid</span><strong>{experiment.data ? (experiment.data.valid ? "Yes" : "No") : "See findings"}</strong></div><div><span>Lock</span>{experiment.data ? <StatusBadge status={experiment.data.lock_status} /> : detail.data ? <StatusBadge status={detail.data.summary.lock_status} /> : <span>Unknown</span>}</div><div><span>Findings</span><strong>{active.length}</strong></div></section>
      {active.length ? <Findings findings={active} /> : <InfoNotice title="No findings returned"><p>The connected service reported no diagnostics for this state. That is not a claim about untested mutations or unobserved runtime paths.</p></InfoNotice>}
      {experiment.data ? <details className="details-panel"><summary>Inspect returned source</summary><pre className="source-view"><code>{experiment.data.source}</code></pre></details> : null}
    </div>
  );
}
