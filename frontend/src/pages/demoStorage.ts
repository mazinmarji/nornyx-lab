import type { ScenarioRun } from "../types";

/**
 * Reload persistence for the nine-step demonstration.
 *
 * Three kinds of state are stored separately, because they carry different
 * evidentiary weight:
 *  - navigation progress (which step the learner reached);
 *  - prediction/choice commitments (the learner's own answers);
 *  - run results (real engine responses the learner actually executed).
 *
 * A run is only ever restored from a stored real response, and is labeled as
 * restored in the UI. Nothing here can mark a step executed that was not: a
 * missing or malformed stored run simply restores nothing, and the page's own
 * gating then re-locks the steps that depend on it.
 */

const PROGRESS_KEY = "nornyx-academy.demo.progress.v1";
const RUNS_KEY = "nornyx-academy.demo.runs.v1";

export interface DemoProgressState {
  index: number;
  prediction: string | null;
  gapPick: string | null;
  gapFound: boolean;
}

export interface DemoRunsState {
  ungoverned: ScenarioRun | null;
  governed: ScenarioRun | null;
}

function isPlausibleRun(value: unknown): value is ScenarioRun {
  if (!value || typeof value !== "object") return false;
  const run = value as Partial<ScenarioRun>;
  return (
    run.api_version === "v1" &&
    typeof run.scenario_id === "string" &&
    typeof run.run_id === "string" &&
    Array.isArray(run.variants) &&
    run.variants.length === 2 &&
    Array.isArray(run.plan)
  );
}

export function loadDemoProgress(): DemoProgressState | null {
  try {
    const raw = window.localStorage.getItem(PROGRESS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<DemoProgressState>;
    if (typeof parsed.index !== "number" || parsed.index < 0) return null;
    return {
      index: Math.floor(parsed.index),
      prediction: typeof parsed.prediction === "string" ? parsed.prediction : null,
      gapPick: typeof parsed.gapPick === "string" ? parsed.gapPick : null,
      gapFound: parsed.gapFound === true,
    };
  } catch {
    return null;
  }
}

export function saveDemoProgress(state: DemoProgressState): void {
  try {
    window.localStorage.setItem(PROGRESS_KEY, JSON.stringify(state));
  } catch {
    // Blocked storage must never break the demonstration.
  }
}

export function loadDemoRuns(): DemoRunsState {
  try {
    const raw = window.localStorage.getItem(RUNS_KEY);
    if (!raw) return { ungoverned: null, governed: null };
    const parsed = JSON.parse(raw) as Partial<Record<keyof DemoRunsState, unknown>>;
    return {
      ungoverned: isPlausibleRun(parsed.ungoverned) ? parsed.ungoverned : null,
      governed: isPlausibleRun(parsed.governed) ? parsed.governed : null,
    };
  } catch {
    return { ungoverned: null, governed: null };
  }
}

export function saveDemoRuns(state: DemoRunsState): void {
  try {
    window.localStorage.setItem(RUNS_KEY, JSON.stringify(state));
  } catch {
    // Ignore: the runs simply will not survive a reload.
  }
}

export function clearDemoStorage(): void {
  try {
    window.localStorage.removeItem(PROGRESS_KEY);
    window.localStorage.removeItem(RUNS_KEY);
  } catch {
    // Nothing to clear.
  }
}
