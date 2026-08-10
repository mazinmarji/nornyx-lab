import { afterEach, describe, expect, it } from "vitest";
import { scenarioFixture } from "../test/fixtures";
import {
  clearDemoStorage,
  loadDemoProgress,
  loadDemoRuns,
  saveDemoProgress,
  saveDemoRuns,
} from "./demoStorage";

afterEach(() => {
  clearDemoStorage();
});

describe("demo reload persistence", () => {
  it("round-trips navigation and prediction state", () => {
    saveDemoProgress({ index: 4, prediction: "Try to publish", gapPick: "gap", gapFound: true });
    expect(loadDemoProgress()).toEqual({
      index: 4,
      prediction: "Try to publish",
      gapPick: "gap",
      gapFound: true,
    });
  });

  it("restores only runs that look like real engine responses", () => {
    saveDemoRuns({ ungoverned: scenarioFixture, governed: null });
    const restored = loadDemoRuns();
    expect(restored.ungoverned?.run_id).toBe(scenarioFixture.run_id);
    expect(restored.governed).toBeNull();
  });

  it("never fabricates a run from malformed or tampered storage", () => {
    window.localStorage.setItem(
      "nornyx-academy.demo.runs.v1",
      JSON.stringify({
        // A truthy object that is not a real ScenarioRun must restore nothing.
        ungoverned: { completed: true },
        governed: { api_version: "v1", scenario_id: "x", variants: [] },
      }),
    );
    const restored = loadDemoRuns();
    expect(restored.ungoverned).toBeNull();
    expect(restored.governed).toBeNull();

    window.localStorage.setItem("nornyx-academy.demo.runs.v1", "not json {");
    expect(loadDemoRuns()).toEqual({ ungoverned: null, governed: null });
  });

  it("ignores malformed progress state", () => {
    window.localStorage.setItem(
      "nornyx-academy.demo.progress.v1",
      JSON.stringify({ index: "six", prediction: 3 }),
    );
    expect(loadDemoProgress()).toBeNull();
  });
});
