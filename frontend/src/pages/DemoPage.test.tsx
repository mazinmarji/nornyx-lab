import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ModeProvider } from "../context/ModeContext";
import { scenarioFixture } from "../test/fixtures";
import { saveDemoProgress, saveDemoRuns } from "./demoStorage";
import { DemoPage } from "./DemoPage";

const story = {
  version: "test",
  screens: [
    { id: "meet", kind: "story", number: 1, title: "Meet the agent", lede: "", body: "", punchline: "", actor: { name: "Agent", abilities: [] } },
    {
      id: "predict-1",
      kind: "predict",
      number: 2,
      title: "What do you think?",
      prediction: { prompt: "What happens?", options: [{ id: "a", label: "Try to publish" }] },
    },
    {
      id: "run-ungoverned",
      kind: "run",
      number: 3,
      title: "Run without governance",
      variant: "ungoverned",
      action_label: "Run without governance",
      observe: { focus: "publish_external" },
    },
    {
      id: "run-governed",
      kind: "run",
      number: 4,
      title: "Run with governance",
      variant: "governed",
      action_label: "Run with governance",
      observe: { focus: "publish_external" },
    },
  ],
};

vi.mock("../api/client", () => ({
  academyApi: {
    demoStory: vi.fn(() => Promise.resolve(story)),
    glossary: vi.fn(() => Promise.resolve({ version: "t", terms: [] })),
    runDemo: vi.fn(() => Promise.resolve(scenarioFixture)),
  },
  toErrorMessage: (cause: unknown) => String(cause),
}));

vi.mock("../context/AcademyContext", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("../context/AcademyContext");
  return {
    ...actual,
    useAcademy: () => ({
      catalog: null,
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

afterEach(() => {
  window.localStorage.clear();
});

describe("DemoPage restored-run provenance", () => {
  it("keeps the restored label on a still-restored variant after re-running the other", async () => {
    // Review finding: one shared flag meant a fresh run of either variant
    // stripped the "restored" warning from the other, still-restored result.
    // Here only the governed run survives restoration; the learner re-runs the
    // ungoverned variant, and the governed result must stay labeled.
    saveDemoProgress({ index: 2, prediction: "Try to publish", gapPick: null, gapFound: false });
    saveDemoRuns({ ungoverned: null, governed: scenarioFixture });

    render(
      <ModeProvider>
        <DemoPage />
      </ModeProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("demo-screen-run-ungoverned")).toBeInTheDocument(),
    );
    // The ungoverned run was not restored, so there is no restored label here.
    expect(screen.queryByTestId("demo-restored-note")).not.toBeInTheDocument();

    await userEvent.click(
      within(screen.getByTestId("demo-screen-run-ungoverned")).getByRole("button", {
        name: /run without governance/i,
      }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("observation-ungoverned")).toBeInTheDocument(),
    );
    // Freshly executed: still no restored label on this screen.
    expect(screen.queryByTestId("demo-restored-note")).not.toBeInTheDocument();

    await userEvent.click(screen.getByTestId("demo-next"));
    await waitFor(() => expect(screen.getByTestId("demo-screen-run-governed")).toBeInTheDocument());
    // The governed result is still the restored one, and must still say so.
    expect(screen.getByTestId("demo-restored-note")).toBeInTheDocument();
  });
});
