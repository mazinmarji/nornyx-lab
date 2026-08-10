import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FeedbackStatus } from "../types";
import { FeedbackPage } from "./FeedbackPage";

// `vi.mock` is hoisted above every top-level statement, so anything its factory
// closes over has to be hoisted with it.
const { api, catalog } = vi.hoisted(() => ({
  api: {
    feedbackStatus: vi.fn(),
    submitCourseFeedback: vi.fn(),
    setFeedbackConsent: vi.fn(),
    syncFeedback: vi.fn(),
    deleteFeedback: vi.fn(),
    resetProgress: vi.fn(),
  },
  catalog: {
    version: "test",
    modules: [
      { id: "F0", title: "Meet the agent" },
      { id: "09", title: "Enforcement" },
    ],
    paths: [],
    concepts: [],
  },
}));

vi.mock("../api/client", () => ({
  academyApi: api,
  toErrorMessage: (cause: unknown) => (cause instanceof Error ? cause.message : String(cause)),
}));

vi.mock("../context/AcademyContext", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("../context/AcademyContext");
  return {
    ...actual,
    useAcademy: () => ({
      catalog,
      dashboard: null,
      platform: null,
      lastRun: null,
      booting: false,
      serviceError: null,
      remediation: null,
      remediationFor: () => null,
      setLastRun: () => undefined,
      refreshProgress: () => Promise.resolve(),
      refreshCatalog: () => Promise.resolve(),
      resetProgress: () => Promise.resolve(),
    }),
  };
});

function status(overrides: Partial<FeedbackStatus> = {}): FeedbackStatus {
  return {
    api_version: "v1",
    schema_id: "nornyx.academy.learner_feedback.v1",
    session_id: "7f21ac1e-4b3d-4c2a-9f10-2b5d6e7a8c90",
    session_started_at: "2026-08-10T12:00:00Z",
    consent_state: "not_asked",
    consent_at: null,
    consent_document_version: "2026.08.1",
    sending_configured: true,
    destination_visibility: "unknown",
    sync: {
      status: "no_consent",
      attempts: 0,
      last_attempt_at: null,
      last_success_at: null,
      last_error_code: null,
      remote_reference: null,
      pending_changes: false,
    },
    module_feedback: [],
    course_feedback: null,
    learner_message: "No feedback has been recorded on this computer yet.",
    consent_disclosure: [
      "What is sent: your 1-5 ratings.",
      "Where it goes: this installation cannot confirm whether the destination is public or private.",
    ],
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <FeedbackPage />
    </MemoryRouter>,
  );
}

describe("course feedback page", () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset();
    api.feedbackStatus.mockResolvedValue(status());
  });

  it("states that it is not an assessment and changes nothing about standing", async () => {
    renderPage();

    await screen.findByTestId("course-feedback-form");
    expect(screen.getByText(/changes your score, your progress/i)).toBeInTheDocument();
    expect(screen.getByText(/not a measurement of whether the course works/i)).toBeInTheDocument();
  });

  it("does not send until every rated question is answered", async () => {
    renderPage();

    await screen.findByTestId("course-feedback-form");
    expect(screen.getByRole("button", { name: /Save my course feedback/i })).toBeDisabled();
    expect(api.submitCourseFeedback).not.toHaveBeenCalled();
  });

  it("sends only the learner's own answers", async () => {
    api.submitCourseFeedback.mockResolvedValue({ saved: true, record_id: 1, status: status() });
    const user = userEvent.setup();
    renderPage();

    await screen.findByTestId("course-feedback-form");
    const groups = screen.getAllByRole("radiogroup");
    await user.click(within(groups[0]).getByRole("radio", { name: /^4/ }));
    await user.click(within(groups[1]).getByRole("radio", { name: /^5/ }));
    await user.click(within(groups[2]).getByRole("radio", { name: /^4/ }));
    await user.click(within(groups[3]).getByRole("radio", { name: /^3/ }));
    await user.click(within(groups[4]).getByRole("radio", { name: "About right" }));
    await user.click(within(groups[5]).getByRole("radio", { name: "Yes" }));
    await user.click(screen.getByRole("button", { name: /Save my course feedback/i }));

    await waitFor(() => expect(api.submitCourseFeedback).toHaveBeenCalledTimes(1));
    const body = api.submitCourseFeedback.mock.calls[0][0];
    // No score, version, session id, or context: the browser sends opinions.
    expect(Object.keys(body).sort()).toEqual([
      "comments",
      "final_confidence",
      "missing_topic",
      "most_confusing_module",
      "most_helpful_module",
      "overall_clarity",
      "overall_difficulty",
      "progression",
      "recommend",
      "usefulness",
    ]);
    expect(body.overall_clarity).toBe(4);
    expect(body.recommend).toBe("yes");
  });

  it("says plainly when the destination cannot be confirmed", async () => {
    renderPage();

    await screen.findByTestId("feedback-record");
    expect(
      screen.getAllByText(/cannot confirm whether the destination is public or private/i).length,
    ).toBeGreaterThan(0);
  });

  it("never pre-checks consent", async () => {
    renderPage();

    await screen.findByTestId("feedback-record");
    for (const box of screen.getAllByRole("checkbox")) expect(box).not.toBeChecked();
  });

  it("offers deletion separately from resetting progress and never claims remote removal", async () => {
    api.feedbackStatus.mockResolvedValue(
      status({
        module_feedback: [
          {
            record_id: 1,
            module_id: "F0",
            created_at: "2026-08-10T12:05:00Z",
            clarity: 4,
            confidence: 3,
            difficulty: "right_level",
            self_assessment: "understood",
            comment: null,
            academy_context: {
              module_status: "complete",
              assessment_score: 1,
              assessment_passed: true,
              assessment_attempts: 1,
              competence_revision: "assessment.2026-08-10",
              learning_path_id: null,
              session_elapsed_seconds: 300,
            },
          },
        ],
      }),
    );
    api.deleteFeedback.mockResolvedValue({
      deleted_module_records: 1,
      deleted_course_records: 0,
      previously_submitted_externally: true,
      limitation:
        "Some of this feedback had already been sent to the maintainers. Deleting the local copy does not remove what was already received, and this installation cannot delete it for you.",
      status: status(),
    });
    const user = userEvent.setup();
    renderPage();

    await screen.findByTestId("feedback-record");
    await user.click(screen.getByRole("button", { name: /Delete my feedback from this computer/i }));

    await waitFor(() => expect(api.deleteFeedback).toHaveBeenCalledTimes(1));
    expect(api.resetProgress).not.toHaveBeenCalled();
    expect(screen.getByTestId("feedback-deleted")).toHaveTextContent(
      /does not remove what was already received/i,
    );
  });

  it("surfaces a service failure instead of pretending the page is empty", async () => {
    api.feedbackStatus.mockRejectedValue(new Error("Cannot reach the local academy service."));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(/Cannot reach/i);
  });
});
