import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RemediationHint } from "./ContentBlocks";
import type { RemediationGuidance, RemediationRegistry } from "../types";

const guidance: RemediationGuidance = {
  code: "ENFORCEMENT_DISABLED",
  title: "The enforcement point was switched off for this run",
  means: "The application did not consult Nornyx before calling the tool.",
  matters: "A contract can be correct and still change nothing without an enforcement point.",
  inspect: "The run configuration for this variant.",
  correction: "Enable the enforcement point and run again.",
  verify: "Re-run with enforcement enabled and confirm a decision event appears.",
};

const registry: RemediationRegistry = {
  api_version: "v1",
  version: "1.0.0",
  provenance_label: "Academy remediation guidance for diagnostic code",
  unknown_code_notice: "No remediation guidance is registered for this code.",
  entries: [guidance],
};

const academy = { remediation: registry, remediationFor: (code: string) => (code === guidance.code ? guidance : null) };
const modeValue = { mode: "guided" as "guided" | "explore" };

vi.mock("../context/AcademyContext", () => ({ useAcademyOptional: () => academy }));
vi.mock("../context/ModeContext", () => ({ useModeOptional: () => modeValue }));

describe("RemediationHint", () => {
  beforeEach(() => {
    modeValue.mode = "guided";
  });

  it("gives all five parts, so a hint is never just an instruction", () => {
    render(<RemediationHint code="ENFORCEMENT_DISABLED" />);
    const panel = screen.getByTestId("remediation-ENFORCEMENT_DISABLED");
    for (const label of [
      "What it means",
      "Why it matters",
      "What to inspect",
      "A correction to consider",
      "How to verify",
    ]) {
      expect(panel).toHaveTextContent(label);
    }
  });

  it("always says how to verify, and never that anything is now fixed", () => {
    render(<RemediationHint code="ENFORCEMENT_DISABLED" />);
    expect(screen.getByTestId("remediation-verify-ENFORCEMENT_DISABLED")).toHaveTextContent(
      /re-run/i,
    );
    // The standing reminder is what stops the panel reading as a verdict.
    const status = screen.getByTestId("remediation-status-ENFORCEMENT_DISABLED");
    expect(status).toHaveTextContent(/does not close the diagnostic/i);

    const panel = screen.getByTestId("remediation-ENFORCEMENT_DISABLED");
    for (const claim of [/\bis now safe\b/i, /\bresolved\b/i, /\bfixed\b/i, /problem solved/i]) {
      expect(panel).not.toHaveTextContent(claim);
    }
  });

  it("states an unknown code rather than guessing guidance for it", () => {
    render(<RemediationHint code="SOME_CODE_WE_DO_NOT_KNOW" />);
    expect(screen.getByTestId("remediation-none-SOME_CODE_WE_DO_NOT_KNOW")).toHaveTextContent(
      "No remediation guidance is registered for this code.",
    );
    expect(screen.queryByTestId("remediation-SOME_CODE_WE_DO_NOT_KNOW")).toBeNull();
  });

  it("attributes the guidance to the academy in Explore mode", () => {
    // Guided mode keeps the panel uncluttered; Explore is where a technical
    // reader is inspecting real Nornyx output beside it and could otherwise
    // take this for runtime output.
    expect(
      screen.queryByTestId("remediation-provenance-ENFORCEMENT_DISABLED"),
    ).toBeNull();

    modeValue.mode = "explore";
    render(<RemediationHint code="ENFORCEMENT_DISABLED" />);
    const provenance = screen.getByTestId("remediation-provenance-ENFORCEMENT_DISABLED");
    expect(provenance).toHaveTextContent("Academy remediation guidance for diagnostic code");
    expect(provenance).toHaveTextContent("not a Nornyx runtime decision");
  });
});
