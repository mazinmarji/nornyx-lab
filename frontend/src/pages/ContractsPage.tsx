import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { academyApi } from "../api/client";
import { ContractGraph } from "../components/Diagrams";
import { Findings } from "../components/ContentBlocks";
import { ErrorNotice, InfoNotice, LoadingState } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useAsyncTask } from "../components/useAsyncTask";
import type { ContractDetail, ContractSummary } from "../types";

type ContractView = "visual" | "source" | "controls" | "diagnostics";

export function ContractsPage() {
  const { contractId } = useParams();
  const summaries = useAsyncTask<ContractSummary[]>();
  const detail = useAsyncTask<ContractDetail>();
  const [selectedId, setSelectedId] = useState(contractId ?? "");
  const [view, setView] = useState<ContractView>("visual");

  useEffect(() => { void summaries.run(() => academyApi.contracts()); }, []); // stable task
  useEffect(() => {
    const target = contractId || selectedId || summaries.data?.[0]?.id;
    if (target && target !== selectedId) setSelectedId(target);
    if (target) void detail.run(() => academyApi.contract(target));
    // Only target identity should trigger a contract read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contractId, selectedId, summaries.data]);

  if (summaries.loading && !summaries.data) return <div className="page"><LoadingState label="Loading authoritative contracts…" /></div>;
  return (
    <div className="page contract-page">
      <header className="page-header tool-header"><div><p className="eyebrow">Authoritative .nyx → graph → generated controls → diagnostics</p><h1>Contract explorer</h1><p>Inspect contract data returned by the academy service. The visual view never becomes a parallel source of truth.</p></div><div className="button-row"><Link className="button button-secondary" to="/builder">Open guided builder</Link><Link className="button button-secondary" to="/graph">Open graph workspace</Link></div></header>
      {summaries.error ? <ErrorNotice message={summaries.error} onRetry={() => void summaries.run(() => academyApi.contracts())} /> : null}
      <section className="contract-shell">
        <aside className="contract-list" aria-label="Available contracts">
          <h2>Contracts</h2>
          {summaries.data?.map((summary) => <button key={summary.id} type="button" className={selectedId === summary.id ? "selected" : ""} onClick={() => setSelectedId(summary.id)}><span><strong>{summary.name}</strong><small>{summary.profile}</small></span><StatusBadge status={summary.lock_status} /></button>)}
        </aside>
        <div className="contract-workspace">
          {detail.loading ? <LoadingState label="Reading contract through Nornyx…" /> : null}
          {detail.error ? <ErrorNotice message={detail.error} onRetry={() => selectedId && void detail.run(() => academyApi.contract(selectedId))} /> : null}
          {detail.data ? <>
            <div className="contract-titlebar"><div><p className="eyebrow">{detail.data.summary.profile} profile</p><h2>{detail.data.summary.name}</h2></div><dl><div><dt>Identities</dt><dd>{detail.data.summary.identity_count}</dd></div><div><dt>Capabilities</dt><dd>{detail.data.summary.capability_count}</dd></div><div><dt>Zones</dt><dd>{detail.data.summary.zone_count}</dd></div><div><dt>Gates</dt><dd>{detail.data.summary.gate_count}</dd></div></dl></div>
            <div className="tab-list" role="tablist" aria-label="Contract views">{(["visual", "source", "controls", "diagnostics"] as ContractView[]).map((tab) => <button type="button" role="tab" aria-selected={view === tab} key={tab} onClick={() => setView(tab)}>{tab === "controls" ? "Generated controls" : tab[0].toUpperCase() + tab.slice(1)}</button>)}</div>
            <div className="tab-panel" role="tabpanel">
              {view === "visual" ? <><ContractGraph nodes={detail.data.nodes} edges={detail.data.edges} /><div className="node-directory"><h3>Semantic elements</h3><div>{detail.data.nodes.map((node) => <article key={node.id}><span>{node.kind}</span><strong>{node.label}</strong><p>{node.detail}</p></article>)}</div></div></> : null}
              {view === "source" ? <><InfoNotice title="The actual contract remains authoritative"><p>{detail.data.formatting_limitation}</p></InfoNotice><pre className="source-view"><code>{detail.data.source}</code></pre></> : null}
              {view === "controls" ? <><InfoNotice title="Generation is not runtime enforcement" tone="warning"><p>A generated control shows intended bindings. It does not prove a runtime imported, invoked, or made that control unavoidable.</p></InfoNotice><div className="object-list">{detail.data.generated_controls.length ? detail.data.generated_controls.map((control, index) => <details key={index}><summary>Generated control {index + 1}</summary><pre><code>{JSON.stringify(control, null, 2)}</code></pre></details>) : <p className="muted">No generated controls were returned.</p>}</div></> : null}
              {view === "diagnostics" ? <>{detail.data.diagnostics.length ? <Findings findings={detail.data.diagnostics} /> : <p className="muted">No diagnostics were returned for this contract.</p>}</> : null}
            </div>
            <p className="safety-boundary"><strong>Assurance boundary:</strong> {detail.data.assurance_boundary}</p>
          </> : null}
        </div>
      </section>
    </div>
  );
}

