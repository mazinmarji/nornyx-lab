import { useId, useState, type ReactNode } from "react";
import { useMode } from "../context/ModeContext";
import type { CausalStep, GlossaryTerm, NamedConcept, Prediction, ScenarioExplanation } from "../types";

/* ---------------------------------------------------------------- mode switch */

export function ModeSwitch() {
  const { mode, setMode } = useMode();
  return (
    <div className="mode-switch" role="group" aria-label="Level of detail" data-testid="mode-switch">
      <button
        type="button"
        className={mode === "guided" ? "is-active" : ""}
        aria-pressed={mode === "guided"}
        onClick={() => setMode("guided")}
      >
        Guided
      </button>
      <button
        type="button"
        className={mode === "explore" ? "is-active" : ""}
        aria-pressed={mode === "explore"}
        onClick={() => setMode("explore")}
      >
        Explore
      </button>
    </div>
  );
}

/** Renders only in Explore mode. Never used to hide a limitation. */
export function ExploreOnly({ children }: { children: ReactNode }) {
  const { explore } = useMode();
  if (!explore) return null;
  return <>{children}</>;
}

/* ------------------------------------------------------------ plain-first term */

/**
 * Plain language first, formal term subordinate. This is presentation only —
 * canonical Nornyx field names in contracts and API responses are untouched.
 */
export function PlainTerm({ plain, formal }: { plain: string; formal?: string }) {
  return (
    <span className="plain-term">
      <strong>{plain}</strong>
      {formal ? <small className="formal-term">{formal}</small> : null}
    </span>
  );
}

/* --------------------------------------------------- "what am I looking at?" */

/**
 * A one-sentence answer to "why does this panel exist", rendered immediately
 * above the technical thing it describes. A learner should never have to infer
 * a panel's purpose from its contents.
 */
export function WhatAmILookingAt({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <p className="what-am-i" data-testid={testId ?? "what-am-i"}>
      <span aria-hidden="true">?</span>
      <span>{children}</span>
    </p>
  );
}

/* ------------------------------------------------------------------ learn line */

export function LearningSentence({ children }: { children: ReactNode }) {
  return (
    <section className="learn-line" data-testid="learning-sentence">
      <p className="eyebrow">In this lesson you will learn</p>
      <p className="learn-sentence">{children}</p>
    </section>
  );
}

/* ------------------------------------------------------------------ prediction */

/**
 * Never scored, and deliberately so: the point is to make the learner commit so
 * the observation can confirm or violate that commitment. Penalising a wrong
 * guess would teach people to withhold one.
 */
export function PredictionStep({
  prediction,
  onCommit,
  committed,
}: {
  prediction: Prediction;
  onCommit: (optionLabel: string) => void;
  committed: string | null;
}) {
  const headingId = useId();
  return (
    <section className="prediction-step" aria-labelledby={headingId} data-testid="prediction-step">
      <p className="eyebrow">Before you run it</p>
      <h2 id={headingId}>{prediction.prompt}</h2>
      <p className="prediction-note">No score, no penalty. Committing to an answer is what makes the result mean something.</p>
      <div className="prediction-options">
        {prediction.options.map((option) => (
          <button
            key={option.label}
            type="button"
            className={committed === option.label ? "prediction-option is-chosen" : "prediction-option"}
            aria-pressed={committed === option.label}
            onClick={() => onCommit(option.label)}
          >
            {option.label}
          </button>
        ))}
      </div>
      {committed ? (
        <p className="prediction-locked" role="status" data-testid="prediction-committed">
          You said <strong>{committed}</strong>. Now run it and see.
        </p>
      ) : null}
    </section>
  );
}

/* ------------------------------------------------------------ visual causality */

export function CausalChain({ steps, title }: { steps: CausalStep[]; title?: string }) {
  if (!steps.length) return null;
  return (
    <div
      className="causal-chain"
      role="group"
      aria-label={title ?? "Why this happened, step by step"}
      tabIndex={0}
      data-testid="causal-chain"
    >
      {steps.map((step, index) => (
        <div className={`causal-step causal-${step.kind}`} key={`${step.label}-${index}`}>
          <strong>{step.label}</strong>
          {step.detail ? <small>{step.detail}</small> : null}
        </div>
      ))}
    </div>
  );
}

/* --------------------------------------------------------------- name the concept */

export function ConceptName({ concept }: { concept: NamedConcept }) {
  return (
    <section className="concept-name" data-testid="concept-name">
      <p className="eyebrow">Now it has a name</p>
      <h2>{concept.plain_name}</h2>
      <p className="concept-formal">
        Technical term: <code>{concept.formal_term}</code>
      </p>
      {concept.definition ? <p>{concept.definition}</p> : null}
    </section>
  );
}

/* ------------------------------------------------------------------- glossary */

export function GlossaryChip({ term }: { term: GlossaryTerm }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <span className="glossary-chip">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        data-testid={`glossary-chip-${term.id}`}
      >
        {term.term}
      </button>
      {open ? (
        <span className="glossary-pop" id={panelId} role="note">
          <strong>{term.plain}</strong>
          <em>Why it matters: {term.why}</em>
          <em>Example: {term.example}</em>
          <ExploreOnly>
            <em>Formally: {term.formal}</em>
          </ExploreOnly>
          <em>In Nornyx: {term.nornyx}</em>
        </span>
      ) : null}
    </span>
  );
}

export function GlossaryStrip({ terms }: { terms: GlossaryTerm[] }) {
  if (!terms.length) return null;
  return (
    <section className="glossary-strip" data-testid="glossary-strip">
      <p className="eyebrow">Words used here</p>
      <div>
        {terms.map((term) => (
          <GlossaryChip key={term.id} term={term} />
        ))}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ the teach-me layer */

/**
 * Renders the explanation derived from the run. It is intentionally incapable
 * of narrating an outcome the engine did not report: when `determinate` is
 * false, that is displayed rather than smoothed over.
 */
export function RunExplanation({ explanation }: { explanation: ScenarioExplanation }) {
  return (
    <section
      className={explanation.determinate ? "run-explanation" : "run-explanation is-indeterminate"}
      aria-labelledby="run-explanation-heading"
      data-testid="run-explanation"
    >
      <div className="explanation-headline">
        <p className="eyebrow">What happened</p>
        <h2 id="run-explanation-heading" data-testid="explanation-headline">
          {explanation.headline}
        </h2>
        <p>{explanation.what_happened}</p>
      </div>

      {explanation.causal_chain.length ? (
        <>
          <WhatAmILookingAt testId="what-am-i-chain">
            This is the order things happened in, and where the outcome was decided.
          </WhatAmILookingAt>
          <CausalChain steps={explanation.causal_chain} />
        </>
      ) : null}

      <div className="explanation-grid">
        <article data-testid="explanation-why">
          <h3>Why it happened</h3>
          <ul>
            {explanation.why.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </article>
        <article data-testid="explanation-nornyx">
          <h3>What Nornyx contributed</h3>
          <p>{explanation.nornyx_role}</p>
        </article>
        <article className="explanation-proves" data-testid="explanation-proves">
          <h3>What this proves</h3>
          <p>{explanation.proves}</p>
        </article>
        <article className="explanation-limits" data-testid="explanation-limits">
          <h3>What this does not prove</h3>
          <ul>
            {explanation.does_not_prove.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
      </div>

      <p className="explanation-remember" data-testid="explanation-remember">
        <span>Remember</span>
        {explanation.remember}
      </p>
    </section>
  );
}
