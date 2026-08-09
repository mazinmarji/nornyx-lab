import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { academyApi } from "../api/client";
import type { AssessmentResult, PublicAssessment } from "../types";
import { ErrorNotice, LoadingState } from "./Feedback";
import { StatusBadge } from "./StatusBadge";
import { useAsyncTask } from "./useAsyncTask";

export function AssessmentPanel({
  assessmentId,
  onComplete,
}: {
  assessmentId: string;
  onComplete?: (result: AssessmentResult) => void | Promise<void>;
}) {
  const definition = useAsyncTask<PublicAssessment>();
  const submission = useAsyncTask<AssessmentResult>();
  const [answers, setAnswers] = useState<string[]>([]);
  const isOrdering = definition.data?.kind === "ordering";
  const allowsMany = isOrdering || ["identify_bypass", "policy_repair"].includes(definition.data?.kind ?? "");

  useEffect(() => {
    setAnswers([]);
    submission.clear();
    void definition.run(() => academyApi.assessment(assessmentId));
    // The task objects are intentionally stable; assessmentId is the resource boundary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assessmentId]);

  const remaining = useMemo(
    () => definition.data?.options.filter((option) => !answers.includes(option.id)) ?? [],
    [answers, definition.data],
  );

  function toggleAnswer(id: string) {
    if (!allowsMany) {
      setAnswers([id]);
      return;
    }
    setAnswers((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  }

  async function submit() {
    const result = await submission.run(() => academyApi.submitAssessment(assessmentId, answers));
    if (result) await onComplete?.(result);
  }

  if (definition.loading) return <LoadingState label="Loading assessment…" />;
  if (definition.error) return <ErrorNotice title="Assessment unavailable" message={definition.error} onRetry={() => void definition.run(() => academyApi.assessment(assessmentId))} />;
  if (!definition.data) return null;

  return (
    <section className="assessment-panel" aria-labelledby={`assessment-${assessmentId}`}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">Knowledge check</p>
          <h2 id={`assessment-${assessmentId}`}>{definition.data.prompt}</h2>
        </div>
        <span className="score-target">Pass at {Math.round(definition.data.minimum_score * 100)}%</span>
      </div>
      {definition.data.context ? <p className="assessment-context">{definition.data.context}</p> : null}

      {isOrdering ? (
        <div className="ordering-exercise">
          <h3>Your sequence</h3>
          {answers.length ? (
            <ol>{answers.map((id) => {
              const option = definition.data?.options.find((item) => item.id === id);
              return <li key={id}><span>{option?.label}</span><button type="button" className="text-button" onClick={() => toggleAnswer(id)}>Remove</button></li>;
            })}</ol>
          ) : <p className="muted">Choose the first step below.</p>}
          <div className="option-stack" aria-label="Available steps">
            {remaining.map((option) => <button type="button" className="choice-button" key={option.id} onClick={() => toggleAnswer(option.id)}>Add next: {option.label}</button>)}
          </div>
        </div>
      ) : (
        <fieldset className="assessment-options">
          <legend className="sr-only">Answer choices</legend>
          {definition.data.options.map((option) => (
            <label key={option.id} className={`assessment-option${answers.includes(option.id) ? " selected" : ""}`}>
              <input
                type={allowsMany ? "checkbox" : "radio"}
                name={`assessment-${assessmentId}`}
                value={option.id}
                checked={answers.includes(option.id)}
                onChange={() => toggleAnswer(option.id)}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </fieldset>
      )}

      {submission.error ? <ErrorNotice title="Answer was not saved" message={submission.error} /> : null}
      <button className="button button-primary" type="button" disabled={!answers.length || submission.loading} onClick={() => void submit()}>
        {submission.loading ? "Checking answer…" : "Check my answer"}
      </button>

      {submission.data ? (
        <div className={`assessment-result ${submission.data.passed ? "assessment-pass" : "assessment-review"}`} aria-live="polite">
          <div className="assessment-result-heading">
            <h3>{submission.data.passed ? "Assessment passed" : "Review and try again"}</h3>
            <StatusBadge status={submission.data.passed ? "complete" : "needs_review"} />
          </div>
          <p><strong>Score: {Math.round(submission.data.score * 100)}%.</strong> {submission.data.explanation}</p>
          {submission.data.feedback.length ? <ul>{submission.data.feedback.map((item, index) => <li key={index}>{item}</li>)}</ul> : null}
          {/* The mastery claim must match the evidence exactly: this item
              tested specific concepts, and passing demonstrates those — not
              every concept the module teaches. */}
          {submission.data.passed && submission.data.concepts_mastered.length ? (
            <p className="assessment-concepts" data-testid="assessment-concepts-demonstrated">
              <strong>Demonstrated:</strong> {submission.data.concepts_mastered.join(", ")}.
            </p>
          ) : null}
          {submission.data.passed && submission.data.module_concepts_pending.length ? (
            <p className="assessment-concepts assessment-concepts-pending" data-testid="assessment-concepts-pending">
              <strong>Not yet demonstrated:</strong>{" "}
              {submission.data.module_concepts_pending.join(", ")} — this lesson teaches these,
              but this check did not test them. Evidence for them comes from later lessons
              and checks.
            </p>
          ) : null}
          {submission.data.passed ? <Link className="text-link" to="/dashboard">See saved progress →</Link> : null}
        </div>
      ) : null}
    </section>
  );
}

