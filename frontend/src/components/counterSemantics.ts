import type { ActionCounter, CounterMeaning } from "../types";

export const counterMeaningLabels: Record<CounterMeaning, string> = {
  prevented_before_execution: "Prevented before execution",
  attempted_not_completed: "Attempted, not completed",
  executed: "Executed",
  not_planned: "Not planned",
  indeterminate: "Cannot conclude",
};

export function deriveCounterMeaning(
  attempts: number | null,
  completions: number | null,
): CounterMeaning {
  if (attempts === null || completions === null) return "indeterminate";
  if (attempts < 0 || completions < 0 || completions > attempts) return "indeterminate";
  if (attempts === 0 && completions === 0) return "prevented_before_execution";
  if (attempts > 0 && completions === 0) return "attempted_not_completed";
  if (attempts > 0 && completions > 0) return "executed";
  return "indeterminate";
}

export function counterIsConsistent(counter: ActionCounter): boolean {
  if (counter.meaning === "not_planned") {
    return counter.attempts === 0 && counter.completions === 0;
  }
  return deriveCounterMeaning(counter.attempts, counter.completions) === counter.meaning;
}

