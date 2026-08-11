import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { academyApi } from "../api/client";
import { ModuleFeedbackCard } from "./LearnerFeedback";
import type { FeedbackStatus } from "../types";

/**
 * The browser must never be the authority on what happened.
 *
 * These specs are aimed at one failure in particular: a UI that says "sent to
 * the maintainers" because it succeeded at *asking*, while the backend recorded
 * a failure. Everything a learner is told here has to come out of the response.
 */

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
    destination_visibility: "private",
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
    learner_message: "Feedback saved on this computer. Nothing has been sent to the maintainers.",
    consent_disclosure: ["What is sent: your 1-5 ratings.", "Where it goes: a private destination."],
    ...overrides,
  };
}

describe("module feedback card", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("is optional and does not open itself", () => {
    render(
      <ModuleFeedbackCard moduleId="F0" moduleTitle="Meet the agent" status={null} onStatus={() => {}} />,
    );
    expect(screen.getByTestId("module-feedback-invite")).toBeInTheDocument();
    expect(screen.queryByTestId("module-feedback-form")).not.toBeInTheDocument();
  });

  it("can be skipped and leaves nothing behind", async () => {
    const submit = vi.spyOn(academyApi, "submitModuleFeedback");
    const user = userEvent.setup();
    render(
      <ModuleFeedbackCard moduleId="F0" moduleTitle="Meet the agent" status={null} onStatus={() => {}} />,
    );

    await user.click(screen.getByRole("button", { name: /Give feedback on this lesson/i }));
    await user.click(screen.getByRole("button", { name: /^Skip$/ }));

    expect(screen.getByTestId("module-feedback-invite")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
  });

  it("will not submit until every rating has actually been chosen", async () => {
    const user = userEvent.setup();
    render(
      <ModuleFeedbackCard moduleId="F0" moduleTitle="Meet the agent" status={null} onStatus={() => {}} />,
    );
    await user.click(screen.getByRole("button", { name: /Give feedback on this lesson/i }));

    const save = screen.getByRole("button", { name: /Save my feedback/i });
    expect(save).toBeDisabled();

    // Answering one of the four questions is not answering them.
    const [clarity] = screen.getAllByRole("radiogroup");
    await user.click(within(clarity).getByRole("radio", { name: /^4/ }));
    expect(save).toBeDisabled();
  });

  it("sends only perception fields and renders the message the server returned", async () => {
    const returned = status({
      learner_message: "Feedback saved on this computer. Nothing has been sent to the maintainers.",
    });
    const submit = vi
      .spyOn(academyApi, "submitModuleFeedback")
      .mockResolvedValue({ saved: true, record_id: 1, status: returned });
    const user = userEvent.setup();
    render(
      <ModuleFeedbackCard moduleId="F0" moduleTitle="Meet the agent" status={null} onStatus={() => {}} />,
    );

    await user.click(screen.getByRole("button", { name: /Give feedback on this lesson/i }));
    const [clarity, confidence] = screen.getAllByRole("radiogroup");
    await user.click(within(clarity).getByRole("radio", { name: /^4/ }));
    await user.click(within(confidence).getByRole("radio", { name: /^3/ }));
    await user.click(screen.getByRole("radio", { name: "About right" }));
    await user.click(screen.getByRole("radio", { name: "I understood it" }));
    await user.type(screen.getByRole("textbox"), "the counters helped");
    await user.click(screen.getByRole("button", { name: /Save my feedback/i }));

    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    const [moduleId, body] = submit.mock.calls[0];
    expect(moduleId).toBe("F0");
    // The exact wire shape: perception only. No score, status, version, or
    // session identifier may be authored by the browser.
    expect(Object.keys(body).sort()).toEqual([
      "clarity",
      "comment",
      "confidence",
      "difficulty",
      "self_assessment",
    ]);
    expect(body).toMatchObject({ clarity: 4, confidence: 3, difficulty: "right_level" });
  });

  it("shows the backend's own words, never a locally composed success", async () => {
    const failed = status({
      consent_state: "granted",
      sync: {
        status: "failed",
        attempts: 1,
        last_attempt_at: "2026-08-10T12:10:00Z",
        last_success_at: null,
        last_error_code: "timeout",
        remote_reference: null,
        pending_changes: true,
      },
      learner_message:
        "Your feedback is saved locally. Sending it to the maintainers is temporarily unavailable.",
    });
    vi.spyOn(academyApi, "submitModuleFeedback").mockResolvedValue({
      saved: true,
      record_id: 1,
      status: failed,
    });
    const user = userEvent.setup();
    let current: FeedbackStatus | null = null;
    const { rerender } = render(
      <ModuleFeedbackCard moduleId="F0" moduleTitle="Meet the agent" status={current} onStatus={(next) => { current = next; }} />,
    );

    await user.click(screen.getByRole("button", { name: /Give feedback on this lesson/i }));
    const [clarity, confidence] = screen.getAllByRole("radiogroup");
    await user.click(within(clarity).getByRole("radio", { name: /^2/ }));
    await user.click(within(confidence).getByRole("radio", { name: /^2/ }));
    await user.click(screen.getByRole("radio", { name: "Too hard" }));
    await user.click(screen.getByRole("radio", { name: /still confused/i }));
    await user.click(screen.getByRole("button", { name: /Save my feedback/i }));

    await waitFor(() => expect(screen.getByTestId("module-feedback-saved")).toBeInTheDocument());
    rerender(
      <ModuleFeedbackCard moduleId="F0" moduleTitle="Meet the agent" status={failed} onStatus={() => {}} />,
    );

    const state = screen.getByTestId("feedback-state");
    expect(state).toHaveTextContent(/saved locally/i);
    expect(state).toHaveTextContent(/temporarily unavailable/i);
    expect(state).not.toHaveTextContent(/sent to the maintainers\./i);
  });

  it("offers consent unchecked and only after explaining what would be sent", async () => {
    vi.spyOn(academyApi, "submitModuleFeedback").mockResolvedValue({
      saved: true,
      record_id: 1,
      status: status(),
    });
    const user = userEvent.setup();
    const { rerender } = render(
      <ModuleFeedbackCard moduleId="F0" moduleTitle="Meet the agent" status={null} onStatus={() => {}} />,
    );

    await user.click(screen.getByRole("button", { name: /Give feedback on this lesson/i }));
    const [clarity, confidence] = screen.getAllByRole("radiogroup");
    await user.click(within(clarity).getByRole("radio", { name: /^5/ }));
    await user.click(within(confidence).getByRole("radio", { name: /^5/ }));
    await user.click(screen.getByRole("radio", { name: "About right" }));
    await user.click(screen.getByRole("radio", { name: "I understood it" }));
    await user.click(screen.getByRole("button", { name: /Save my feedback/i }));

    await waitFor(() => expect(screen.getByTestId("module-feedback-saved")).toBeInTheDocument());
    rerender(
      <ModuleFeedbackCard moduleId="F0" moduleTitle="Meet the agent" status={status()} onStatus={() => {}} />,
    );

    const consent = screen.getByRole("checkbox", { name: /Send my feedback to the Nornyx maintainers/i });
    expect(consent).not.toBeChecked();
    expect(screen.getByText(/What is sent: your 1-5 ratings\./)).toBeInTheDocument();
    expect(screen.getByText(/Off by default\. Nothing has been sent\./)).toBeInTheDocument();
  });

  it("states that sending is unavailable as installation configuration, not learner error", async () => {
    vi.spyOn(academyApi, "submitModuleFeedback").mockResolvedValue({
      saved: true,
      record_id: 1,
      status: status({ sending_configured: false }),
    });
    const user = userEvent.setup();
    const unconfigured = status({ sending_configured: false });
    const { rerender } = render(
      <ModuleFeedbackCard moduleId="F0" moduleTitle="Meet the agent" status={null} onStatus={() => {}} />,
    );

    await user.click(screen.getByRole("button", { name: /Give feedback on this lesson/i }));
    const [clarity, confidence] = screen.getAllByRole("radiogroup");
    await user.click(within(clarity).getByRole("radio", { name: /^3/ }));
    await user.click(within(confidence).getByRole("radio", { name: /^3/ }));
    await user.click(screen.getByRole("radio", { name: "About right" }));
    await user.click(screen.getByRole("radio", { name: "I understood it" }));
    await user.click(screen.getByRole("button", { name: /Save my feedback/i }));

    await waitFor(() => expect(screen.getByTestId("module-feedback-saved")).toBeInTheDocument());
    rerender(
      <ModuleFeedbackCard moduleId="F0" moduleTitle="Meet the agent" status={unconfigured} onStatus={() => {}} />,
    );

    expect(screen.getByTestId("module-feedback-consent-unavailable")).toHaveTextContent(
      /not configured to send feedback/i,
    );
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("warns about personal information next to the free-text box", async () => {
    const user = userEvent.setup();
    render(
      <ModuleFeedbackCard moduleId="F0" moduleTitle="Meet the agent" status={null} onStatus={() => {}} />,
    );
    await user.click(screen.getByRole("button", { name: /Give feedback on this lesson/i }));

    expect(
      screen.getByText(/Please do not include personal or sensitive information\./),
    ).toBeInTheDocument();
  });

  it("keeps a failure to save from being reported as success", async () => {
    vi.spyOn(academyApi, "submitModuleFeedback").mockRejectedValue(
      new Error("Cannot reach the local academy service."),
    );
    const user = userEvent.setup();
    render(
      <ModuleFeedbackCard moduleId="F0" moduleTitle="Meet the agent" status={null} onStatus={() => {}} />,
    );

    await user.click(screen.getByRole("button", { name: /Give feedback on this lesson/i }));
    const [clarity, confidence] = screen.getAllByRole("radiogroup");
    await user.click(within(clarity).getByRole("radio", { name: /^4/ }));
    await user.click(within(confidence).getByRole("radio", { name: /^4/ }));
    await user.click(screen.getByRole("radio", { name: "About right" }));
    await user.click(screen.getByRole("radio", { name: "I understood it" }));
    await user.click(screen.getByRole("button", { name: /Save my feedback/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/Cannot reach/i));
    expect(screen.queryByTestId("module-feedback-saved")).not.toBeInTheDocument();
  });
});
