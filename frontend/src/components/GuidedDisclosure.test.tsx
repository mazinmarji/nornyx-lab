import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { ModeProvider } from "../context/ModeContext";
import type { ContentBlock, DecisionTrace } from "../types";
import { ContentBlocks } from "./ContentBlocks";
import { DecisionCard } from "./DecisionCard";
import { ModeSwitch } from "./Teaching";

afterEach(() => {
  window.localStorage.clear();
});

const decisionWithoutZones: DecisionTrace = {
  requested: true,
  effect: "allow",
  code: "ALLOWED",
  reason: "The typed request satisfied the composed contract.",
  identity: "identity.intake_agent",
  capability: "read_customer_case",
  resource: "resource.case",
  source_zone: null,
  target_zone: null,
  policy_refs: [],
  gate_refs: [],
  approval_state: "not_applicable",
  enforcement_point: "application pre-call boundary",
  coverage_surface: "named synchronous surface",
  basis: [],
};

describe("guided-mode progressive disclosure", () => {
  it("never renders 'Unknown → Unknown' for a decision without a zone crossing", () => {
    render(<DecisionCard decision={decisionWithoutZones} />);
    expect(screen.getByText("No zone crossing in this decision")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Unknown → Unknown");
  });

  it("keeps raw implementation metadata one mode switch away, not in guided view", async () => {
    const block: ContentBlock = {
      id: "b1",
      kind: "concept",
      title: "A concept",
      body: "Plain explanation the learner reads first.",
      language: null,
      rows: [],
      metadata: { decision_at: "2026-06-01T12:00:00Z", observed_subject_revision: "git:abc" },
    };
    render(
      <ModeProvider>
        <ModeSwitch />
        <ContentBlocks blocks={[block]} />
      </ModeProvider>,
    );

    // Guided: the prose is there, the implementation fields are not.
    expect(screen.getByText(/plain explanation/i)).toBeInTheDocument();
    expect(screen.queryByText(/decision at/)).not.toBeInTheDocument();

    // Explore: the same fields remain fully discoverable.
    await userEvent.click(screen.getByRole("button", { name: "Explore" }));
    expect(screen.getByText("Inspect structured details")).toBeInTheDocument();
    expect(screen.getByText(/decision at/)).toBeInTheDocument();
  });
});
