import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { EvidenceFinding } from "../types";
import { CausalFindings, groupDiagnostics } from "./BuilderDiagnostics";

function finding(code: string, message: string): EvidenceFinding {
  return { status: "fail", code, message, path: null, missing_fields: [] };
}

/** The real diagnostic mix produced by removing identity.case_analyst. */
const rootCauses = [
  finding("AN_DELEGATOR_UNKNOWN", "Unknown delegator identity 'identity.case_analyst'."),
  finding("AN_IDENTITY_UNKNOWN", "Membership references unknown identity 'identity.case_analyst'."),
];
const lockConsequences = [
  finding("AN_LOCK_ARTIFACT_MISMATCH", "Locked artifact hash for 'capability_matrix.json' does not match."),
  finding("AN_LOCK_RECORD_MISMATCH", "Locked agent_identities digests do not match."),
  finding("AN_LOCK_SOURCE_STALE", "Lock field 'source_contract_digest' does not match."),
];

describe("groupDiagnostics", () => {
  it("separates root-cause diagnostics from lock consequences", () => {
    const { primary, consequences } = groupDiagnostics([...lockConsequences, ...rootCauses]);
    expect(primary.map((item) => item.code)).toEqual([
      "AN_DELEGATOR_UNKNOWN",
      "AN_IDENTITY_UNKNOWN",
    ]);
    expect(consequences).toHaveLength(3);
  });

  it("treats lock findings as primary when nothing else failed", () => {
    const { primary, consequences } = groupDiagnostics(lockConsequences);
    expect(primary).toHaveLength(3);
    expect(consequences).toHaveLength(0);
  });
});

describe("CausalFindings", () => {
  it("shows the primary problem first and keeps every Nornyx finding visible", () => {
    render(<CausalFindings findings={[...lockConsequences, ...rootCauses]} />);

    expect(screen.getByTestId("primary-problem-heading")).toBeInTheDocument();
    const consequenceGroup = screen.getByTestId("consequence-findings");
    expect(consequenceGroup.querySelector("summary")?.textContent).toMatch(/3 lock findings/);

    // Nothing suppressed: all five exact codes render.
    for (const item of [...rootCauses, ...lockConsequences]) {
      expect(screen.getByText(item.code)).toBeInTheDocument();
    }
    // The grouping declares its provenance as academy presentation.
    expect(consequenceGroup.textContent).toMatch(/academy presentation/i);
    // The primary section renders before the consequence group in the DOM.
    const container = screen.getByTestId("primary-problem-heading").parentElement!;
    const order = [...container.querySelectorAll("[data-testid]")].map((node) =>
      node.getAttribute("data-testid"),
    );
    expect(order.indexOf("primary-problem-heading")).toBeLessThan(
      order.indexOf("consequence-findings"),
    );
  });
});
