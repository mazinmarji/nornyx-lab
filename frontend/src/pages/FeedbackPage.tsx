import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { academyApi, toErrorMessage } from "../api/client";
import { ErrorNotice, LoadingState } from "../components/Feedback";
import {
  ChoiceGroup,
  ConsentPanel,
  FeedbackStateNotice,
  PRIVACY_NOTE,
  RatingScale,
} from "../components/LearnerFeedback";
import { useAcademy } from "../context/AcademyContext";
import type {
  CourseFeedbackRequest,
  FeedbackDifficulty,
  FeedbackRecommendation,
  FeedbackStatus,
} from "../types";

/**
 * Course-level feedback, plus the controls for consent and local deletion.
 *
 * This page is also where a learner can see exactly what is held about them and
 * remove it. Deletion here is deliberately separate from "reset progress" on
 * the dashboard: wanting to start the curriculum again is not the same as
 * withdrawing what you said about it, and coupling the two would quietly
 * destroy one when someone asked for the other.
 */

const DIFFICULTY_OPTIONS: { value: FeedbackDifficulty; label: string }[] = [
  { value: "too_easy", label: "Too easy" },
  { value: "right_level", label: "About right" },
  { value: "too_hard", label: "Too hard" },
];

const RECOMMEND_OPTIONS: { value: FeedbackRecommendation; label: string }[] = [
  { value: "yes", label: "Yes" },
  { value: "maybe", label: "Maybe" },
  { value: "no", label: "No" },
];

export function FeedbackPage() {
  const { catalog } = useAcademy();
  const [status, setStatus] = useState<FeedbackStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [deletion, setDeletion] = useState<string | null>(null);

  const [clarity, setClarity] = useState<number | null>(null);
  const [progression, setProgression] = useState<number | null>(null);
  const [usefulness, setUsefulness] = useState<number | null>(null);
  const [finalConfidence, setFinalConfidence] = useState<number | null>(null);
  const [difficulty, setDifficulty] = useState<FeedbackDifficulty | null>(null);
  const [recommend, setRecommend] = useState<FeedbackRecommendation | null>(null);
  const [mostHelpful, setMostHelpful] = useState("");
  const [mostConfusing, setMostConfusing] = useState("");
  const [missingTopic, setMissingTopic] = useState("");
  const [comments, setComments] = useState("");

  useEffect(() => {
    let active = true;
    academyApi
      .feedbackStatus()
      .then((value) => active && setStatus(value))
      .catch((cause) => active && setLoadError(toErrorMessage(cause)));
    return () => {
      active = false;
    };
  }, []);

  const complete =
    clarity !== null &&
    progression !== null &&
    usefulness !== null &&
    finalConfidence !== null &&
    difficulty !== null &&
    recommend !== null;

  async function submit() {
    if (!complete) return;
    setBusy(true);
    setActionError(null);
    try {
      const body: CourseFeedbackRequest = {
        overall_clarity: clarity,
        progression,
        usefulness,
        final_confidence: finalConfidence,
        overall_difficulty: difficulty,
        recommend,
        most_helpful_module: mostHelpful || null,
        most_confusing_module: mostConfusing || null,
        missing_topic: missingTopic.trim() ? missingTopic : null,
        comments: comments.trim() ? comments : null,
      };
      const response = await academyApi.submitCourseFeedback(body);
      setStatus(response.status);
      setSaved(true);
    } catch (cause) {
      setActionError(toErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function setConsent(granted: boolean) {
    setBusy(true);
    setActionError(null);
    try {
      setStatus(await academyApi.setFeedbackConsent(granted));
    } catch (cause) {
      setActionError(toErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function retrySend() {
    setBusy(true);
    setActionError(null);
    try {
      setStatus(await academyApi.syncFeedback());
    } catch (cause) {
      setActionError(toErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function deleteFeedback() {
    setBusy(true);
    setActionError(null);
    try {
      const response = await academyApi.deleteFeedback();
      setStatus(response.status);
      setSaved(false);
      setDeletion(
        response.limitation ||
          `Deleted ${response.deleted_module_records} lesson response(s) and ` +
            `${response.deleted_course_records} course response(s) from this computer.`,
      );
    } catch (cause) {
      setActionError(toErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  if (loadError) {
    return (
      <div className="page">
        <header className="page-header">
          <h1>Feedback</h1>
        </header>
        <ErrorNotice message={loadError} />
      </div>
    );
  }
  if (!status) return <div className="page"><LoadingState label="Loading feedback…" /></div>;

  const modules = catalog?.modules ?? [];

  return (
    <div className="page feedback-page">
      <header className="page-header">
        <p className="eyebrow">Optional · saved on this computer first</p>
        <h1>Tell us how the course went</h1>
        <p>
          This is research instrumentation, not an assessment. Nothing you say here changes your
          score, your progress, what the academy records as demonstrated, or your standing. It is
          also not a measurement of whether the course works — it is what one learner reported.
        </p>
      </header>

      <FeedbackStateNotice status={status} />
      {actionError ? <ErrorNotice title="That did not go through" message={actionError} /> : null}
      {deletion ? (
        <p className="feedback-state feedback-state-ok" role="status" data-testid="feedback-deleted">
          {deletion}
        </p>
      ) : null}

      {saved ? (
        <section className="feedback-card" data-testid="course-feedback-saved">
          <h2>Thank you — your course feedback is saved.</h2>
          <ConsentPanel
            status={status}
            onChange={(value) => void setConsent(value)}
            busy={busy}
            testId="course-feedback-consent"
          />
          {status.sync.status === "failed" ? (
            <button type="button" className="button button-secondary" disabled={busy} onClick={() => void retrySend()}>
              Try sending again
            </button>
          ) : null}
          <button type="button" className="text-button" onClick={() => setSaved(false)}>
            Change my answers
          </button>
        </section>
      ) : (
        <section className="feedback-card" data-testid="course-feedback-form">
          <RatingScale name="overall-clarity" legend="Overall, how clear was the course?" value={clarity} onChange={setClarity} />
          <RatingScale name="progression" legend="Did the order of topics make sense?" value={progression} onChange={setProgression} />
          <RatingScale name="usefulness" legend="How useful was it for work you actually do?" value={usefulness} onChange={setUsefulness} />
          <RatingScale name="final-confidence" legend="How confident do you feel now?" value={finalConfidence} onChange={setFinalConfidence} />
          <ChoiceGroup name="course-difficulty" legend="Overall difficulty" options={DIFFICULTY_OPTIONS} value={difficulty} onChange={setDifficulty} />
          <ChoiceGroup name="recommend" legend="Would you recommend this course?" options={RECOMMEND_OPTIONS} value={recommend} onChange={setRecommend} />

          <div className="form-grid">
            <label>
              <span>Most helpful module (optional)</span>
              <select value={mostHelpful} onChange={(event) => setMostHelpful(event.target.value)}>
                <option value="">No answer</option>
                {modules.map((module) => (
                  <option key={module.id} value={module.id}>{module.title}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Most confusing module (optional)</span>
              <select value={mostConfusing} onChange={(event) => setMostConfusing(event.target.value)}>
                <option value="">No answer</option>
                {modules.map((module) => (
                  <option key={module.id} value={module.id}>{module.title}</option>
                ))}
              </select>
            </label>
          </div>

          <label className="feedback-comment">
            <span>Was anything missing?</span>
            <textarea rows={2} maxLength={2000} value={missingTopic} onChange={(event) => setMissingTopic(event.target.value)} placeholder="Optional" />
          </label>
          <label className="feedback-comment">
            <span>Anything else you want to tell us?</span>
            <textarea rows={4} maxLength={4000} value={comments} onChange={(event) => setComments(event.target.value)} placeholder="Optional" />
            <small>{PRIVACY_NOTE}</small>
          </label>

          <div className="button-row">
            <button type="button" className="button button-primary" disabled={!complete || busy} onClick={() => void submit()}>
              {busy ? "Saving…" : "Save my course feedback"}
            </button>
            <Link className="button button-secondary" to="/dashboard">Not now</Link>
          </div>
        </section>
      )}

      <section className="feedback-card" data-testid="feedback-record">
        <div className="section-heading compact-heading">
          <div>
            <p className="eyebrow">Your feedback on this computer</p>
            <h2>{status.module_feedback.length} lesson response(s){status.course_feedback ? " · 1 course response" : ""}</h2>
          </div>
        </div>
        {status.module_feedback.length ? (
          <ul className="feedback-record-list">
            {status.module_feedback.map((record) => (
              <li key={record.record_id}>
                <strong>{modules.find((module) => module.id === record.module_id)?.title ?? record.module_id}</strong>
                <span>clarity {record.clarity}/5 · confidence {record.confidence}/5</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">Nothing recorded yet.</p>
        )}
        <ConsentPanel
          status={status}
          onChange={(value) => void setConsent(value)}
          busy={busy}
          testId="feedback-record-consent"
        />
        <div className="button-row">
          <button type="button" className="button button-quiet-danger" disabled={busy} onClick={() => void deleteFeedback()}>
            Delete my feedback from this computer
          </button>
        </div>
        <p className="muted">
          Deleting your feedback does not touch your progress or your results. If some of it has
          already been sent to the maintainers, deleting the local copy does not remove what was
          already received.
        </p>
      </section>
    </div>
  );
}
