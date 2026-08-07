import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type { CurriculumModule } from "../types";
import {
  AdvancedLessonControls,
  hasAdvancedConfiguration,
  hasLessonConfiguration,
  initialAdvancedConfiguration,
  LessonInteraction,
  lessonInteractionFor,
} from "./LessonInteraction";

const destinations = [
  ["F0", "governed-ungoverned-demo", "/demo"],
  ["F1", "model-variability-lab", "/diagnostics"],
  ["F2", "context-composer", "/demo"],
  ["F3", "tool-side-effect-simulator", "/graph"],
  ["F4", "agent-runtime-graph", "/graph"],
  ["F5", "evaluation-workbench", "/diagnostics"],
  ["00", "assistant-agent-simulator", "/demo"],
  ["01", "control-drift-diff", "/contracts"],
  ["02", "claim-layer-sorter", "/evidence"],
  ["03", "pdp-pep-wiring-canvas", "/graph"],
  ["04", "identity-authority-graph", "/graph"],
  ["05", "trust-zone-injection", "/demo"],
  ["06", "decision-matrix", "/approvals"],
  ["07", "composition-layer-view", "/contracts"],
  ["08", "approval-simulator", "/approvals"],
  ["09", "enforcement-failure-lab", "/diagnostics"],
  ["10", "evidence-explorer", "/evidence"],
  ["11", "lock-replay-workbench", "/evidence"],
  ["12", "assurance-claim-editor", "/evidence"],
  ["13", "bypass-explorer", "/diagnostics"],
  ["14", "visual-contract-builder", "/builder"],
  ["15", "profile-lock-workbench", "/contracts"],
  ["16", "authorization-request-workbench", "/contracts"],
  ["17", "occurrence-drift-timeline", "/evidence"],
  ["18", "crewai-adapter-lab", "/diagnostics"],
  ["19", "langgraph-occurrence-suite", "/graph"],
  ["20", "conformance-supply-chain-lab", "/diagnostics"],
  ["21", "authoring-ci-pipeline", "/builder"],
  ["22", "forge-release-network", "/graph"],
  ["23", "assurance-audit-workbench", "/evidence"],
  ["24", "capstone-workspace", "/capstone"],
] as const;

function moduleFixture(id = "14", interaction = "visual-contract-builder"): CurriculumModule {
  return {
    id,
    legacy_lab_id: id,
    kind: "lab",
    title: "Example lesson",
    eyebrow: "Lab",
    summary: "A safe example.",
    why_it_matters: "It matters.",
    difficulty: "beginner",
    minutes: 15,
    prerequisites: [],
    concepts: [],
    outcomes: [],
    interaction,
    scenario_id: null,
    completion: { requires_execution: true, assessment_id: "assessment.example", minimum_score: 80, required_challenges: [] },
    migration_classification: "adapt for GUI",
    status: "not_started",
    score: null,
  };
}

describe("lessonInteractionFor", () => {
  it.each(destinations)("maps module %s with %s to %s", (moduleId, interaction, route) => {
    expect(lessonInteractionFor(moduleId, interaction).route).toBe(route);
  });

  it("uses the interaction fallback when catalog metadata no longer matches the module mapping", () => {
    expect(lessonInteractionFor("14", "evidence-explorer").route).toBe("/evidence");
  });
});

describe("advanced configuration support", () => {
  it("matches the advanced service's accepted input fields", () => {
    expect(hasAdvancedConfiguration("19")).toBe(false);
    expect(hasAdvancedConfiguration("22")).toBe(true);
    expect(hasAdvancedConfiguration("23")).toBe(true);
  });

  it("marks every lesson whose controls must be included in the run request", () => {
    for (const moduleId of ["F1", "F2", "F3", "F4", "F5", "22", "23"]) {
      expect(hasLessonConfiguration(moduleId)).toBe(true);
    }
    for (const moduleId of ["F0", "00", "19", "24"]) {
      expect(hasLessonConfiguration(moduleId)).toBe(false);
    }
  });
});

describe("LessonInteraction", () => {
  it("links to guided practice and says it is separate from the structured run", () => {
    render(<MemoryRouter><LessonInteraction module={moduleFixture()} /></MemoryRouter>);

    expect(screen.getByRole("link", { name: "Open visual contract builder" })).toHaveAttribute("href", "/builder");
    expect(screen.getByText(/choices there do not change the inputs or result/i)).toBeInTheDocument();
    expect(screen.getByText("Visual Contract Builder")).toBeInTheDocument();
  });
});

describe("AdvancedLessonControls", () => {
  it("explains that Lab 19 always runs its comprehensive fixed coverage", () => {
    render(<AdvancedLessonControls moduleId="19" value={{}} onChange={() => undefined} />);

    expect(screen.getByText("One comprehensive LangGraph suite")).toBeInTheDocument();
    expect(screen.getByText(/accepts no learner input fields/i)).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("submits the complete Lab 22 configuration when approval evidence changes", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<AdvancedLessonControls moduleId="22" value={initialAdvancedConfiguration("22")} onChange={onChange} />);

    await user.selectOptions(screen.getByRole("combobox", { name: /Approval evidence/i }), "missing");

    expect(onChange).toHaveBeenLastCalledWith({ approval_state: "missing", include_inert_bypass: true });
  });

  it("submits the Lab 23 direct-bypass selection", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<AdvancedLessonControls moduleId="23" value={initialAdvancedConfiguration("23")} onChange={onChange} />);

    await user.click(screen.getByRole("checkbox", { name: /Include the direct-bypass negative control/i }));

    expect(onChange).toHaveBeenLastCalledWith({ include_direct_bypass: false });
  });
});
