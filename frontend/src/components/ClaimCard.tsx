import type { ClaimInterpretation } from "../types";
import { StatusBadge } from "./StatusBadge";

export function ClaimCard({ claim }: { claim: ClaimInterpretation }) {
  return (
    <article className={`claim-card claim-${claim.status}`}>
      <div className="claim-heading">
        <h4>{claim.claim}</h4>
        <StatusBadge status={claim.status} />
      </div>
      <p>{claim.because}</p>
      {claim.evidence_refs.length ? (
        <p className="meta-line"><strong>Evidence:</strong> {claim.evidence_refs.join(", ")}</p>
      ) : null}
      <p className="limitation"><strong>Limit:</strong> {claim.limitation}</p>
    </article>
  );
}

