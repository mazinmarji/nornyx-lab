import type { ClaimStatus, EvidenceStatus, ModuleStatus } from "../types";

type Status =
  | ClaimStatus
  | EvidenceStatus
  | ModuleStatus
  | "allow"
  | "deny"
  | "approval_required"
  | "not_evaluated"
  | "error"
  | "ready"
  | "running"
  | "failed"
  | "unavailable";

const labels: Record<string, string> = {
  pass: "Pass",
  fail: "Fail",
  missing: "Missing",
  unknown: "Unknown",
  supported: "Supported",
  unsupported: "Unsupported",
  indeterminate: "Indeterminate",
  not_started: "Not started",
  in_progress: "In progress",
  needs_review: "Needs review",
  complete: "Complete",
  allow: "Allow",
  deny: "Deny",
  approval_required: "Approval required",
  not_evaluated: "Not evaluated",
  error: "Error",
  ready: "Ready",
  running: "Running",
  failed: "Failed",
  unavailable: "Unavailable",
};

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`status-badge status-${status}`}>
      <span className="status-dot" aria-hidden="true" />
      {labels[status] ?? status.replaceAll("_", " ")}
    </span>
  );
}

