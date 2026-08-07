import { useAcademyOptional } from "../context/AcademyContext";
import { useModeOptional } from "../context/ModeContext";
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

/**
 * Remediation guidance for one diagnostic, rendered inside that diagnostic so
 * it cannot drift away from the code it belongs to.
 *
 * Two things this must not do. It must not imply that following it settles
 * anything — so "How to verify" is always rendered, never conditionally, and a
 * standing line says the diagnostic is not closed by reading this. And it must
 * not read as Nornyx output: the provenance line in Explore mode says whose
 * guidance this is, because sitting next to a real diagnostic code is exactly
 * where someone would assume otherwise.
 */
export function RemediationHint({ code }: { code: string }) {
  // Optional reads: the guidance is additive, and must never be able to break
  // the rendering of the diagnostic it annotates.
  const academy = useAcademyOptional();
  const mode = useModeOptional()?.mode ?? "guided";
  const remediation = academy?.remediation ?? null;
  const guidance = academy?.remediationFor(code) ?? null;

  if (!guidance) {
    return (
      <p className="remediation-none" data-testid={`remediation-none-${code}`}>
        {remediation?.unknown_code_notice ?? "No remediation guidance is registered for this code."}
      </p>
    );
  }

  return (
    <details className="remediation" data-testid={`remediation-${code}`}>
      <summary>What this means, and what to check</summary>
      <div className="remediation-body">
        <h4>{guidance.title}</h4>
        <dl>
          <div><dt>What it means</dt><dd>{guidance.means}</dd></div>
          <div><dt>Why it matters</dt><dd>{guidance.matters}</dd></div>
          <div><dt>What to inspect</dt><dd>{guidance.inspect}</dd></div>
          <div><dt>A correction to consider</dt><dd>{guidance.correction}</dd></div>
          <div className="remediation-verify">
            <dt>How to verify</dt>
            <dd data-testid={`remediation-verify-${code}`}>{guidance.verify}</dd>
          </div>
        </dl>
        <p className="remediation-status" data-testid={`remediation-status-${code}`}>
          Reading this does not close the diagnostic. Re-run the step and read the result.
        </p>
        {mode === "explore" ? (
          <p className="remediation-provenance" data-testid={`remediation-provenance-${code}`}>
            {remediation?.provenance_label ?? "Academy remediation guidance for diagnostic code"}{" "}
            <code>{code}</code>. Academy teaching material, not a Nornyx runtime decision.
          </p>
        ) : null}
      </div>
    </details>
  );
}

export function Findings({ findings }: { findings: EvidenceFinding[] }) {
  return (
    <div className="findings-list">
      {findings.map((finding, index) => (
        <article className={`finding finding-${finding.status}`} key={`${finding.code}-${index}`}>
          <StatusBadge status={finding.status} />
          <div><h3><code>{finding.code}</code></h3><p>{finding.message}</p>{finding.path ? <p className="meta-line">Path: <code>{finding.path}</code></p> : null}{finding.missing_fields.length ? <p className="meta-line">Missing fields: {finding.missing_fields.join(", ")}</p> : null}<RemediationHint code={finding.code} /></div>
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
