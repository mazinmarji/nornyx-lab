import type { ContentBlock, EvidenceFinding } from "../types";
import { StatusBadge } from "./StatusBadge";

function DataTable({ rows }: { rows: Record<string, unknown>[] }) {
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  if (!rows.length) return <p className="muted">No rows returned.</p>;
  return (
    <div className="comparison-table-wrap">
      <table>
        <thead><tr>{columns.map((column) => <th key={column} scope="col">{column.replaceAll("_", " ")}</th>)}</tr></thead>
        <tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{typeof row[column] === "string" ? String(row[column]) : JSON.stringify(row[column])}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function StructuredDetails({ metadata }: { metadata: Record<string, unknown> }) {
  const entries = Object.entries(metadata);
  if (!entries.length) return null;
  return (
    <details className="structured-details">
      <summary>Inspect structured details</summary>
      <dl>{entries.map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd><code>{typeof value === "string" ? value : JSON.stringify(value)}</code></dd></div>)}</dl>
    </details>
  );
}

export function Findings({ findings }: { findings: EvidenceFinding[] }) {
  return (
    <div className="findings-list">
      {findings.map((finding, index) => (
        <article className={`finding finding-${finding.status}`} key={`${finding.code}-${index}`}>
          <StatusBadge status={finding.status} />
          <div><h3><code>{finding.code}</code></h3><p>{finding.message}</p>{finding.path ? <p className="meta-line">Path: <code>{finding.path}</code></p> : null}{finding.missing_fields.length ? <p className="meta-line">Missing fields: {finding.missing_fields.join(", ")}</p> : null}</div>
        </article>
      ))}
    </div>
  );
}

export function ContentBlocks({ blocks }: { blocks: ContentBlock[] }) {
  const visibleBlocks = blocks.filter((block) => block.metadata.hidden_from_learner !== true);
  return (
    <div className="content-blocks">
      {visibleBlocks.map((block) => {
        if (block.kind === "code") return <section key={block.id} className="content-block"><h2>{block.title}</h2><pre><code>{block.body}</code></pre><StructuredDetails metadata={block.metadata} /></section>;
        if (["decision_table", "ledger_comparison", "diagnostics"].includes(block.kind)) return <section key={block.id} className={`content-block block-${block.kind}`}><h2>{block.title}</h2>{block.body ? <p>{block.body}</p> : null}<DataTable rows={block.rows} /><StructuredDetails metadata={block.metadata} /></section>;
        return <section key={block.id} className={`content-block block-${block.kind}`}><h2>{block.title}</h2>{block.body.split("\n").filter(Boolean).map((paragraph, index) => <p key={index}>{paragraph}</p>)}{block.rows.length ? <DataTable rows={block.rows} /> : null}<StructuredDetails metadata={block.metadata} /></section>;
      })}
    </div>
  );
}
