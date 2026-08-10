import type { EvidenceFinding } from "../types";
import { Findings } from "./ContentBlocks";

/**
 * Causal presentation of workbench diagnostics.
 *
 * One root configuration defect (say, removing an identity that memberships,
 * delegations, and relations still reference) also invalidates every locked
 * digest of the mutated copy, so the learner used to face a flat list where
 * three real problems drowned among a dozen AN_LOCK_* rows. The lock rows are
 * real Nornyx diagnostics and every one is still rendered with its exact code
 * and message — this module only decides presentation order and grouping,
 * which is academy teaching material, not a runtime judgement.
 */

const CONSEQUENCE_CODE = /^AN_LOCK_/;

export function groupDiagnostics(findings: EvidenceFinding[]): {
  primary: EvidenceFinding[];
  consequences: EvidenceFinding[];
} {
  const primary = findings.filter((finding) => !CONSEQUENCE_CODE.test(finding.code));
  const consequences = findings.filter((finding) => CONSEQUENCE_CODE.test(finding.code));
  // With no non-lock diagnostic, the lock findings ARE the primary problem
  // (an edit was made without refreshing the copy's lock) — nothing to bury.
  if (!primary.length) return { primary: consequences, consequences: [] };
  return { primary, consequences };
}

export function CausalFindings({ findings }: { findings: EvidenceFinding[] }) {
  const { primary, consequences } = groupDiagnostics(findings);
  if (!findings.length) return null;
  return (
    <div className="causal-findings">
      {consequences.length ? (
        <p className="eyebrow" data-testid="primary-problem-heading">
          Primary problem{primary.length === 1 ? "" : "s"}
        </p>
      ) : null}
      <Findings findings={primary} />
      {consequences.length ? (
        <details className="consequence-findings" data-testid="consequence-findings">
          <summary>
            Caused by the problem{primary.length === 1 ? "" : "s"} above: {consequences.length}{" "}
            lock finding{consequences.length === 1 ? "" : "s"}
          </summary>
          <p className="muted">
            The mutation changed the contract copy, so every digest recorded in its lock no
            longer matches. These are real Nornyx lock diagnostics, shown in full below; they
            resolve when the primary problem is fixed and the copy&rsquo;s lock is refreshed.
            This grouping is academy presentation, not part of the Nornyx result.
          </p>
          <Findings findings={consequences} />
        </details>
      ) : null}
    </div>
  );
}
