import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { AssessmentResult, PublicAssessment } from "../types";
import { AssessmentPanel } from "./AssessmentPanel";

const publicAssessment: PublicAssessment = {
  id: "assessment.F0",
  module_id: "F0",
  kind: "assurance_correction",
  concepts: ["assurance boundary", "evidence"],
  prompt: "Which is the strongest honest conclusion?",
  context: "",
  options: [
    { id: "bounded", label: "The named wrapped path prevented this publication." },
    { id: "everything", label: "Nornyx made the entire agent safe." },
  ],
  minimum_score: 1,
};

const passResult: AssessmentResult = {
  assessment_id: "assessment.F0",
  module_id: "F0",
  score: 1,
  passed: true,
  correct_answers: ["bounded"],
  explanation: "Only the named cooperative surface is in scope.",
  feedback: ["Only the named cooperative surface is in scope."],
  concepts_mastered: ["assurance boundary", "evidence"],
  concepts_needing_review: [],
  module_concepts_pending: ["agent", "assistant", "prompt injection"],
};

vi.mock("../api/client", () => ({
  academyApi: {
    assessment: vi.fn(() => Promise.resolve(publicAssessment)),
    submitAssessment: vi.fn(() => Promise.resolve(passResult)),
  },
  toErrorMessage: (cause: unknown) => String(cause),
}));

describe("AssessmentPanel mastery reporting", () => {
  it("reports only the demonstrated concepts and names what still needs evidence", async () => {
    render(
      <MemoryRouter>
        <AssessmentPanel assessmentId="assessment.F0" />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText(/strongest honest conclusion/i)).toBeInTheDocument(),
    );

    await userEvent.click(screen.getByLabelText(/named wrapped path/i));
    await userEvent.click(screen.getByRole("button", { name: /check my answer/i }));

    const demonstrated = await screen.findByTestId("assessment-concepts-demonstrated");
    expect(demonstrated.textContent).toContain("assurance boundary");
    expect(demonstrated.textContent).toContain("evidence");
    // The success message must not imply mastery of untested module concepts.
    expect(demonstrated.textContent).not.toContain("prompt injection");

    const pending = screen.getByTestId("assessment-concepts-pending");
    expect(pending.textContent).toContain("prompt injection");
    expect(pending.textContent).toMatch(/not yet demonstrated/i);
  });
});
