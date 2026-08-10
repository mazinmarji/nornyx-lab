import { useState, type ReactNode } from "react";
import { academyApi, toErrorMessage } from "../api/client";
import type {
  FeedbackDifficulty,
  FeedbackStatus,
  FeedbackUnderstanding,
  ModuleFeedbackRequest,
} from "../types";

/**
 * Optional learner feedback.
 *
 * Three rules this file exists to hold:
 *
 * 1. **It never blocks learning.** The card is skippable, nothing is required,
 *    and closing it has no effect on progress.
 * 2. **The server owns the message.** Whatever a learner is told about saving,
 *    consent, and sending is `status.learner_message`, produced by the backend.
 *    The browser must never compose "sent to the maintainers" from its own
 *    state, because the browser does not know whether it was.
 * 3. **Consent is opt-in, unchecked, and explained before it is offered.**
 */

export const RATING_LABELS: Record<number, string> = {
  1: "Not at all",
  2: "A little",
  3: "Somewhat",
  4: "Mostly",
  5: "Completely",
};

const DIFFICULTY_OPTIONS: { value: FeedbackDifficulty; label: string }[] = [
  { value: "too_easy", label: "Too easy" },
  { value: "right_level", label: "About right" },
  { value: "too_hard", label: "Too hard" },
];

const UNDERSTANDING_OPTIONS: { value: FeedbackUnderstanding; label: string }[] = [
  { value: "understood", label: "I understood it" },
  { value: "partly_understood", label: "I partly understood it" },
  { value: "still_confused", label: "I'm still confused" },
];

export const PRIVACY_NOTE =
  "Please do not include personal or sensitive information.";

export function RatingScale({
  name,
  legend,
  value,
  onChange,
}: {
  name: string;
  legend: string;
  value: number | null;
  onChange: (next: number) => void;
}) {
  return (
    <fieldset className="feedback-scale">
      <legend>{legend}</legend>
      <div className="feedback-scale-options" role="radiogroup" aria-label={legend}>
        {[1, 2, 3, 4, 5].map((score) => (
          <label key={score} className={value === score ? "feedback-chip feedback-chip-on" : "feedback-chip"}>
            <input
              type="radio"
              name={name}
              value={score}
              checked={value === score}
              onChange={() => onChange(score)}
            />
            <strong>{score}</strong>
            <small>{RATING_LABELS[score]}</small>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function ChoiceGroup<T extends string>({
  name,
  legend,
  options,
  value,
  onChange,
}: {
  name: string;
  legend: string;
  options: { value: T; label: string }[];
  value: T | null;
  onChange: (next: T) => void;
}) {
  return (
    <fieldset className="feedback-scale">
      <legend>{legend}</legend>
      <div className="feedback-scale-options" role="radiogroup" aria-label={legend}>
        {options.map((option) => (
          <label
            key={option.value}
            className={value === option.value ? "feedback-chip feedback-chip-on" : "feedback-chip"}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
            />
            <small>{option.label}</small>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/**
 * The state the backend reports, rendered verbatim.
 *
 * Deliberately dumb: it takes `status.learner_message` and shows it. If this
 * component ever starts deciding what to say, the UI can drift from what the
 * record actually holds — which is the failure this design exists to prevent.
 */
export function FeedbackStateNotice({ status }: { status: FeedbackStatus | null }) {
  if (!status) return null;
  const tone =
    status.sync.status === "failed" ? "feedback-state-warning" : "feedback-state-ok";
  return (
    <p className={`feedback-state ${tone}`} role="status" data-testid="feedback-state">
      {status.learner_message}
    </p>
  );
}

/**
 * The consent control.
 *
 * Never pre-checked, and the disclosure is above the checkbox rather than
 * behind a link: a learner should be able to read what would be sent without
 * doing anything first.
 */
export function ConsentPanel({
  status,
  onChange,
  busy,
  // Explicit rather than a fixed constant: a page may legitimately show this
  // control in more than one place, and two elements sharing a test id makes
  // every query against it ambiguous.
  testId,
}: {
  status: FeedbackStatus;
  onChange: (granted: boolean) => void;
  busy: boolean;
  testId: string;
}) {
  const granted = status.consent_state === "granted";
  if (!status.sending_configured) {
    return (
      <div className="feedback-consent" data-testid={`${testId}-unavailable`}>
        <p className="muted">
          Feedback is saved locally. This installation is not configured to send feedback to the
          maintainers, so there is nothing to opt in to.
        </p>
      </div>
    );
  }
  return (
    <div className="feedback-consent" data-testid={testId}>
      <details open={!granted}>
        <summary>What would be sent to the maintainers</summary>
        <ul>
          {status.consent_disclosure.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </details>
      <label className="toggle-field">
        <input
          type="checkbox"
          checked={granted}
          disabled={busy}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>
          <strong>Send my feedback to the Nornyx maintainers.</strong>
          <small>
            {granted
              ? "You can turn this off at any time. Turning it off stops future sending; it cannot recall anything already received."
              : "Off by default. Nothing has been sent."}
          </small>
        </span>
      </label>
    </div>
  );
}

function FeedbackShell({
  title,
  eyebrow,
  children,
  testId,
}: {
  title: string;
  eyebrow: string;
  children: ReactNode;
  testId: string;
}) {
  return (
    <section className="feedback-card" data-testid={testId} aria-labelledby={`${testId}-title`}>
      <div className="section-heading compact-heading">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2 id={`${testId}-title`}>{title}</h2>
        </div>
      </div>
      {children}
    </section>
  );
}

/**
 * Module feedback, shown after the lesson's own flow.
 *
 * It appears below the assessment because it is about a lesson the learner has
 * already been through. Asking mid-teaching would interrupt the thing being
 * measured.
 */
export function ModuleFeedbackCard({
  moduleId,
  moduleTitle,
  status,
  onStatus,
}: {
  moduleId: string;
  moduleTitle: string;
  status: FeedbackStatus | null;
  onStatus: (next: FeedbackStatus) => void;
}) {
  const [open, setOpen] = useState(false);
  const [clarity, setClarity] = useState<number | null>(null);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [difficulty, setDifficulty] = useState<FeedbackDifficulty | null>(null);
  const [understanding, setUnderstanding] = useState<FeedbackUnderstanding | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const existing = status?.module_feedback.find((record) => record.module_id === moduleId) ?? null;
  const complete = clarity !== null && confidence !== null && difficulty !== null && understanding !== null;

  async function submit() {
    if (!complete) return;
    setBusy(true);
    setError(null);
    try {
      const body: ModuleFeedbackRequest = {
        clarity,
        confidence,
        difficulty,
        self_assessment: understanding,
        comment: comment.trim() ? comment : null,
      };
      const response = await academyApi.submitModuleFeedback(moduleId, body);
      onStatus(response.status);
      setSaved(true);
    } catch (cause) {
      setError(toErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function setConsent(granted: boolean) {
    setBusy(true);
    setError(null);
    try {
      onStatus(await academyApi.setFeedbackConsent(granted));
    } catch (cause) {
      setError(toErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  if (!open && !saved) {
    return (
      <section className="feedback-invite" data-testid="module-feedback-invite">
        <p>
          <strong>Optional:</strong> was this lesson clear? Thirty seconds of feedback helps improve
          it. It has no effect on your progress or your results.
        </p>
        <button type="button" className="button button-secondary" onClick={() => setOpen(true)}>
          Give feedback on this lesson
        </button>
      </section>
    );
  }

  if (saved) {
    return (
      <FeedbackShell
        eyebrow="Optional feedback · not part of your results"
        title="Thank you"
        testId="module-feedback-saved"
      >
        <FeedbackStateNotice status={status} />
        {status ? (
          <ConsentPanel
            status={status}
            onChange={(value) => void setConsent(value)}
            busy={busy}
            testId="module-feedback-consent"
          />
        ) : null}
        {error ? <p className="feedback-state feedback-state-warning">{error}</p> : null}
        <button
          type="button"
          className="text-button"
          onClick={() => {
            setSaved(false);
            setOpen(true);
          }}
        >
          Change my answers
        </button>
      </FeedbackShell>
    );
  }

  return (
    <FeedbackShell
      eyebrow="Optional feedback · not part of your results"
      title={`How was “${moduleTitle}”?`}
      testId="module-feedback-form"
    >
      <p className="muted">
        This is about how the lesson felt to you. It is kept separate from what you have
        demonstrated, and it never changes your score, your progress, or what the academy says you
        have learned.
      </p>
      {existing ? (
        <p className="muted" data-testid="module-feedback-existing">
          You already gave feedback on this lesson. Sending it again replaces your earlier answers.
        </p>
      ) : null}

      <RatingScale name="clarity" legend="How clear was this lesson?" value={clarity} onChange={setClarity} />
      <RatingScale
        name="confidence"
        legend="How confident do you feel about this topic now?"
        value={confidence}
        onChange={setConfidence}
      />
      <ChoiceGroup
        name="difficulty"
        legend="How difficult was it?"
        options={DIFFICULTY_OPTIONS}
        value={difficulty}
        onChange={setDifficulty}
      />
      <ChoiceGroup
        name="understanding"
        legend="How well do you think you understood it?"
        options={UNDERSTANDING_OPTIONS}
        value={understanding}
        onChange={setUnderstanding}
      />

      <label className="feedback-comment">
        <span>What was confusing or missing?</span>
        <textarea
          rows={3}
          maxLength={2000}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          placeholder="Optional"
        />
        <small>{PRIVACY_NOTE}</small>
      </label>

      {error ? <p className="feedback-state feedback-state-warning" role="alert">{error}</p> : null}

      <div className="button-row">
        <button
          type="button"
          className="button button-primary"
          disabled={!complete || busy}
          onClick={() => void submit()}
        >
          {busy ? "Saving…" : "Save my feedback"}
        </button>
        <button type="button" className="button button-secondary" onClick={() => setOpen(false)}>
          Skip
        </button>
      </div>
    </FeedbackShell>
  );
}
