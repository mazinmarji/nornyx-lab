import { render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ModeProvider } from "../context/ModeContext";
import type { CurriculumModule, StageMap } from "../types";
import { CurriculumPage } from "./CurriculumPage";

/**
 * Coverage is derived from the real authored stage data, never from a
 * hard-coded module list: if stages.json maps a new module to a step, this
 * test fails until the curriculum page gives that module a direct link.
 */
// Vitest runs with the frontend directory as cwd (see package.json scripts).
const stagesPath = resolve(process.cwd(), "../src/nornyx_lab/academy/content/stages.json");
const stagesData = JSON.parse(readFileSync(stagesPath, "utf-8")) as StageMap & {
  entry: { module_ids: string[] };
};

const stageMap: StageMap = {
  api_version: "v1",
  version: String((stagesData as unknown as { version: string }).version ?? "test"),
  entry: { module_ids: stagesData.entry.module_ids, why: "entry" },
  stages: stagesData.stages.map((stage) => ({
    ...stage,
    completed_steps: 0,
    total_steps: stage.steps.length,
  })),
  understood_concepts: [],
  next_concepts: [],
};

const steppedModuleIds = [
  ...new Set(
    stageMap.stages.flatMap((stage) => stage.steps.flatMap((step) => step.module_ids)),
  ),
];

function moduleFixture(id: string, status: CurriculumModule["status"]): CurriculumModule {
  return {
    id,
    legacy_lab_id: null,
    kind: "lab",
    title: `Module ${id} title`,
    eyebrow: "Stage",
    summary: "",
    why_it_matters: "",
    difficulty: "beginner",
    minutes: 10,
    prerequisites: [],
    concepts: [],
    outcomes: [],
    interaction: "",
    scenario_id: null,
    completion: {
      requires_execution: true,
      assessment_id: `assessment.${id}`,
      minimum_score: 0.8,
      required_challenges: [],
    },
    migration_classification: null,
    status,
    score: null,
  };
}

const allIds = [...new Set([...steppedModuleIds, ...stagesData.entry.module_ids])];
const modules = allIds.map((id, index) =>
  moduleFixture(id, index % 2 === 0 ? "complete" : "not_started"),
);

vi.mock("../api/client", () => ({
  academyApi: {
    stages: () => Promise.resolve(stageMap),
    health: () => Promise.resolve({ status: "ok", api_version: "v1" }),
    platform: () => Promise.reject(new Error("not needed")),
    catalog: () => Promise.reject(new Error("not needed")),
    progress: () => Promise.reject(new Error("not needed")),
    remediation: () => Promise.reject(new Error("not needed")),
  },
  toErrorMessage: (cause: unknown) => String(cause),
}));

vi.mock("../context/AcademyContext", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("../context/AcademyContext");
  return {
    ...actual,
    useAcademy: () => ({
      catalog: { version: "test", modules, paths: [], concepts: [] },
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

function renderPage() {
  return render(
    <MemoryRouter>
      <ModeProvider>
        <CurriculumPage />
      </ModeProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  window.localStorage.clear();
});

describe("CurriculumPage module reachability", () => {
  it("gives every module mapped by the stage data a direct lesson link", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId("stage-1")).toBeInTheDocument());

    for (const moduleId of steppedModuleIds) {
      const links = document.querySelectorAll(
        `a[href="/lessons/${encodeURIComponent(moduleId)}"]`,
      );
      expect(
        links.length,
        `module ${moduleId} is mapped by stages.json but has no direct curriculum link`,
      ).toBeGreaterThan(0);
    }
  });

  it("keeps per-module completion status visible on multi-module steps", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId("stage-1")).toBeInTheDocument());

    const multiStep = stageMap.stages
      .flatMap((stage) => stage.steps)
      .find((step) => step.module_ids.length > 1);
    expect(multiStep, "the authored stage data no longer has a multi-module step").toBeDefined();

    const stepElement = screen.getByTestId(`stage-step-${multiStep!.number}`);
    for (const moduleId of multiStep!.module_ids) {
      const link = stepElement.querySelector(
        `a[href="/lessons/${encodeURIComponent(moduleId)}"]`,
      );
      expect(
        link,
        `step ${multiStep!.number} does not link module ${moduleId}`,
      ).not.toBeNull();
    }
  });

  it("keeps the conceptual step primary and hides engineering ids in guided mode", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId("stage-1")).toBeInTheDocument());

    // Guided mode: step names are the primary headings; raw module ids like
    // "03" or "F5" must not appear as naked identifiers in the step body.
    const step = screen.getByTestId("stage-step-14");
    expect(step.textContent).toContain("Decisions");
    expect(step.querySelector("code")).toBeNull();
  });
});
