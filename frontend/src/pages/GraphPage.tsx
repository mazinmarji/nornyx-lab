import { useEffect, useState } from "react";
import { academyApi } from "../api/client";
import { ContractGraph } from "../components/Diagrams";
import { ErrorNotice, InfoNotice, LoadingState } from "../components/Feedback";
import { useAsyncTask } from "../components/useAsyncTask";
import type { ContractDetail } from "../types";

export function GraphPage() {
  const task = useAsyncTask<ContractDetail>();
  const [contractId, setContractId] = useState("atlas");
  const [kind, setKind] = useState("all");
  useEffect(() => { void task.run(() => academyApi.contract(contractId)); }, [contractId]); // stable task
  const nodes = task.data?.nodes.filter((node) => kind === "all" || node.kind === kind) ?? [];
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = task.data?.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)) ?? [];
  const kinds = [...new Set(task.data?.nodes.map((node) => node.kind) ?? [])];
  return (
    <div className="page graph-page">
      <header className="page-header"><p className="eyebrow">Identity · capability · trust zone · delegation · handoff</p><h1>Agent and trust-zone graph</h1><p>Explore semantic nodes and relationships returned from the actual contract. Lines describe declaration; they do not prove runtime use.</p></header>
      <section className="filter-bar"><label><span>Contract</span><select value={contractId} onChange={(event) => setContractId(event.target.value)}><option value="atlas">Atlas</option><option value="ledger">Ledger</option></select></label><label><span>Element type</span><select value={kind} onChange={(event) => setKind(event.target.value)}><option value="all">All elements</option>{kinds.map((item) => <option value={item} key={item}>{item}</option>)}</select></label></section>
      {task.loading ? <LoadingState label="Building semantic graph…" /> : null}
      {task.error ? <ErrorNotice message={task.error} /> : null}
      {task.data ? <><ContractGraph nodes={nodes} edges={edges} /><InfoNotice title="How to read this graph"><p>Nodes and edges are declared by <strong>{task.data.summary.name}</strong>. Runtime evidence is required to show which identity, relationship, generated artifact, and control were actually exercised.</p></InfoNotice><div className="graph-directory">{nodes.map((node) => <article key={node.id}><span>{node.kind}</span><h2>{node.label}</h2><p>{node.detail}</p><details><summary>Fields</summary><pre><code>{JSON.stringify(node.fields, null, 2)}</code></pre></details></article>)}</div></> : null}
    </div>
  );
}

