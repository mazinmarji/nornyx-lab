import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { scenarioFixture } from "../test/fixtures";
import { saveDemoProgress, saveDemoRuns } from "../pages/demoStorage";
import { AcademyProvider, useAcademy } from "./AcademyContext";

const dashboard = {
  learner_id: "local",
  modules: [],
  completed_modules: 0,
  total_modules: 31,
  completion_percent: 0,
  current_module_id: null,
  last_activity: null,
  concepts_mastered: [],
  concepts_needing_review: [],
  concepts_pending_evidence: [],
  capstone_status: "not_started",
  advanced_standing: null,
};

vi.mock("../api/client", () => ({
  academyApi: {
    health: vi.fn(() => Promise.resolve({ status: "ok", api_version: "v1" })),
    platform: vi.fn(() => Promise.reject(new Error("not needed"))),
    catalog: vi.fn(() => Promise.resolve({ version: "t", modules: [], paths: [], concepts: [] })),
    progress: vi.fn(() => Promise.resolve(dashboard)),
    remediation: vi.fn(() => Promise.reject(new Error("not needed"))),
    resetProgress: vi.fn(() => Promise.resolve(dashboard)),
  },
  toErrorMessage: (cause: unknown) => String(cause),
}));

function ResetButton() {
  const { resetProgress } = useAcademy();
  return (
    <button type="button" onClick={() => void resetProgress()}>
      Reset everything
    </button>
  );
}

afterEach(() => {
  window.localStorage.clear();
});

describe("resetProgress", () => {
  it("clears the browser-persisted demo state along with the learner record", async () => {
    // The review finding: a reset learner record could resurrect predictions
    // and run results from localStorage on the next demo visit.
    saveDemoProgress({ index: 5, prediction: "Try to publish", gapPick: "gap", gapFound: true });
    saveDemoRuns({ ungoverned: scenarioFixture, governed: scenarioFixture });
    expect(window.localStorage.getItem("nornyx-academy.demo.progress.v1")).not.toBeNull();
    expect(window.localStorage.getItem("nornyx-academy.demo.runs.v1")).not.toBeNull();

    render(
      <AcademyProvider>
        <ResetButton />
      </AcademyProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /reset everything/i }));

    await waitFor(() => {
      expect(window.localStorage.getItem("nornyx-academy.demo.progress.v1")).toBeNull();
      expect(window.localStorage.getItem("nornyx-academy.demo.runs.v1")).toBeNull();
    });
  });
});
