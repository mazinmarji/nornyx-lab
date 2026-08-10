import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { Dashboard } from "../types";
import { DashboardPage } from "./DashboardPage";

/**
 * A learner whose earlier passes were earned under a superseded competence
 * definition. The distinction that matters: "gamma" was never attempted,
 * while "alpha"/"beta" were demonstrated and must be demonstrated again.
 * Telling this learner they never did the work would be its own false claim.
 */
const dashboard: Dashboard = {
  learner_id: "local",
  modules: [],
  completed_modules: 1,
  total_modules: 31,
  completion_percent: 3.2,
  current_module_id: "MX",
  last_activity: "2026-08-10T00:00:00Z",
  concepts_mastered: [],
  concepts_needing_review: [],
  concepts_pending_evidence: ["alpha", "beta", "gamma"],
  concepts_requiring_redemonstration: ["alpha", "beta"],
  capstone_status: "complete",
  advanced_standing: {
    capstone_content_complete: true,
    capstone_concepts_demonstrated: false,
    independent_authorship_demonstrated: false,
    transfer_demonstrated: false,
    advanced_competence_demonstrated: false,
    requires_redemonstration: true,
    note: "Not yet advanced. Still required: capstone concept evidence. Previous work covering capstone concept evidence was earned under an older competence definition and must be demonstrated again.",
  },
};

vi.mock("../api/client", () => ({
  academyApi: { exportProgress: vi.fn() },
  toErrorMessage: (cause: unknown) => String(cause),
}));

vi.mock("../context/AcademyContext", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("../context/AcademyContext");
  return {
    ...actual,
    useAcademy: () => ({
      catalog: { version: "t", modules: [], paths: [], concepts: [] },
      dashboard,
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

describe("DashboardPage stale-evidence reporting", () => {
  it("separates concepts needing re-demonstration from never-attempted ones", async () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("concepts-requiring-redemonstration")).toBeInTheDocument(),
    );

    const stale = screen.getByTestId("concepts-requiring-redemonstration");
    expect(stale.textContent).toContain("alpha");
    expect(stale.textContent).toContain("beta");
    // "gamma" was never attempted; it must not be presented as needing a redo.
    expect(stale.textContent).not.toContain("gamma");

    // The learner is told the work happened and why it no longer counts.
    expect(screen.getByText(/under an older definition/i)).toBeInTheDocument();
    expect(screen.getByText(/still in your record/i)).toBeInTheDocument();

    // Mastery is not claimed for any of it.
    expect(screen.getByTestId("concepts-pending-evidence").textContent).toContain("gamma");
  });

  it("reports advanced standing as not demonstrated without erasing the history", async () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );
    const standing = await screen.findByTestId("dashboard-advanced-standing");
    expect(standing.textContent).toMatch(/not yet demonstrated/i);
    expect(standing.textContent).toMatch(/demonstrated again/i);
  });
});
