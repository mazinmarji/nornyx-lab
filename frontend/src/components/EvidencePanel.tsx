import type { EvidencePackage } from "../types";
import { RemediationHint } from "./ContentBlocks";
import { StatusBadge } from "./StatusBadge";

function observedLabel(value: boolean | null): string {
  if (value === null) return "Not established";
  return value ? "Observed" : "Not observed";
}

export function EvidencePanel({ evidence }: { evidence: EvidencePackage }) {
  return (
    <section className="evidence-panel">
      <div className="section-heading compact-heading">
        <div>
          <p className="eyebrow">Evidence package</p>
          <h3>{evidence.producer}</h3>
        </div>
        <StatusBadge status={evidence.validation_status} />
      </div>
      <dl className="field-list evidence-summary">
        <div><dt>Producer type</dt><dd>{evidence.producer_type}</dd></div>
        <div><dt>Schema</dt><dd>{evidence.schema_id}</dd></div>
        <div><dt>Integrity</dt><dd>{observedLabel(evidence.integrity_observed)}</dd></div>
        <div><dt>Completeness</dt><dd>{observedLabel(evidence.completeness_observed)}</dd></div>
      </dl>
      <div className="findings-list" aria-label="Evidence validation findings">
        {evidence.findings.length ? evidence.findings.map((finding, index) => (
          <article key={`${finding.code}-${index}`} className={`finding finding-${finding.status}`}>
            <StatusBadge status={finding.status} />
            <div>
              <h4><code>{finding.code}</code></h4>
              <p>{finding.message}</p>
              {finding.path ? <p className="meta-line">Path: <code>{finding.path}</code></p> : null}
              {finding.missing_fields.length ? (
                <p className="meta-line">Missing: {finding.missing_fields.join(", ")}</p>
              ) : null}
              {/* This panel renders findings itself rather than through
                  `Findings`, so the hint has to be attached here too — a
                  diagnostic without its guidance on one surface and with it on
                  another is worse than not having it at all. */}
              <RemediationHint code={finding.code} />
            </div>
          </article>
        )) : <p className="muted">No validation findings were returned.</p>}
      </div>
      <details className="details-panel evidence-events">
        <summary>Inspect normalized evidence events ({evidence.events.length})</summary>
        {evidence.events.length ? (
          <ol>
            {evidence.events.map((event, index) => (
              <li key={index}><pre><code>{JSON.stringify(event, null, 2)}</code></pre></li>
            ))}
          </ol>
        ) : <p className="muted">No normalized evidence events were returned.</p>}
      </details>
      <p className="limitation"><strong>Evidence limit:</strong> {evidence.limitation}</p>
    </section>
  );
}
