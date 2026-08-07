import type { ActionCounter } from "../types";
import { counterIsConsistent, counterMeaningLabels } from "./counterSemantics";

const tone: Record<ActionCounter["meaning"], string> = {
  prevented_before_execution: "safe",
  attempted_not_completed: "warning",
  executed: "danger",
  not_planned: "neutral",
  indeterminate: "unknown",
};

function value(value: number | null): string {
  return value === null ? "?" : String(value);
}

export function CounterCard({ counter, compact = false }: { counter: ActionCounter; compact?: boolean }) {
  const consistent = counterIsConsistent(counter);
  const effectiveMeaning: ActionCounter["meaning"] = consistent ? counter.meaning : "indeterminate";
  const attempts = consistent ? counter.attempts : null;
  const completions = consistent ? counter.completions : null;
  return (
    <article
      className={`counter-card counter-${tone[effectiveMeaning]} ${!consistent ? "counter-inconsistent" : ""} ${compact ? "counter-compact" : ""}`}
      data-counter-state={effectiveMeaning}
    >
      <p className="counter-action">{counter.action}</p>
      <div className="counter-values" aria-label={`${value(attempts)} attempts and ${value(completions)} completions`}>
        <div>
          <strong>{value(attempts)}</strong>
          <span>Attempts</span>
        </div>
        <span className="counter-divider" aria-hidden="true">/</span>
        <div>
          <strong>{value(completions)}</strong>
          <span>Completions</span>
        </div>
      </div>
      <p className="counter-meaning">{counterMeaningLabels[effectiveMeaning]}</p>
      {!consistent ? (
        <p className="counter-consistency-warning" role="alert">
          Counter values and the reported meaning disagree. Treat this result as indeterminate; the service reported {value(counter.attempts)} attempts and {value(counter.completions)} completions with “{counterMeaningLabels[counter.meaning]}”.
        </p>
      ) : null}
    </article>
  );
}
