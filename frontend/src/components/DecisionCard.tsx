import type { DecisionTrace } from "../types";
import { StatusBadge } from "./StatusBadge";

export function DecisionCard({ decision, index = 0 }: { decision: DecisionTrace; index?: number }) {
  return (
    <article className="decision-card">
      <div className="decision-heading">
        <div>
          <p className="eyebrow">Authorization decision {index + 1}</p>
          <h3>{decision.code}</h3>
        </div>
        <StatusBadge status={decision.effect} />
      </div>
      <p className="decision-reason">{decision.reason}</p>
      <dl className="field-list decision-grid">
        <div><dt>Identity</dt><dd>{decision.identity}</dd></div>
        <div><dt>Capability</dt><dd>{decision.capability}</dd></div>
        <div><dt>Resource</dt><dd>{decision.resource}</dd></div>
        {/* "Unknown → Unknown" read like a defect. Absent zones mean the
            decision did not involve a zone crossing, so say that. */}
        <div><dt>Trust zones</dt><dd>{decision.source_zone || decision.target_zone ? `${decision.source_zone ?? "unspecified"} → ${decision.target_zone ?? "unspecified"}` : "No zone crossing in this decision"}</dd></div>
        <div><dt>Policy</dt><dd>{decision.policy_refs.length ? decision.policy_refs.join(", ") : "No policy reference reported"}</dd></div>
        <div><dt>Gate</dt><dd>{decision.gate_refs.length ? decision.gate_refs.join(", ") : "No gate reported"}</dd></div>
        <div><dt>Approval</dt><dd>{decision.approval_state.replaceAll("_", " ")}</dd></div>
        <div><dt>Enforcement point</dt><dd>{decision.enforcement_point}</dd></div>
        <div className="field-wide"><dt>Covered surface</dt><dd>{decision.coverage_surface}</dd></div>
      </dl>
      {decision.basis.length ? (
        <details className="details-panel">
          <summary>Inspect decision basis</summary>
          <ul className="basis-list">
            {decision.basis.map((basis, basisIndex) => (
              <li key={`${basis.ref}-${basisIndex}`}>
                <code>{basis.kind}</code> <strong>{basis.ref}</strong>{basis.detail ? ` — ${basis.detail}` : ""}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </article>
  );
}

