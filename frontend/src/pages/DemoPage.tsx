import { useCallback, useEffect, useMemo, useState } from "react";
import { academyApi, toErrorMessage } from "../api/client";
import { AssessmentPanel } from "../components/AssessmentPanel";
import { CounterCard } from "../components/CounterCard";
import { ErrorNotice, InfoNotice, LoadingState } from "../components/Feedback";
import { ScenarioResults } from "../components/ScenarioResults";
import {
  ExploreOnly,
  GlossaryStrip,
  ModeSwitch,
  PredictionStep,
  RunExplanation,
  WhatAmILookingAt,
} from "../components/Teaching";
import { useAsyncTask } from "../components/useAsyncTask";
import { useAcademy } from "../context/AcademyContext";
import { useMode } from "../context/ModeContext";
import type { ActionCounter, DemoOptions, DemoStory, DemoStoryScreen, GlossaryTerm, ScenarioRun } from "../types";

export const defaultDemoOptions: DemoOptions = {
  injection_enabled: true,
  enforcement_enabled: true,
  enforcement_failure: false,
  failure_mode: "fail_closed",
  identity_ref: "identity.research_assistant",
  observed_subject_revision: null,
  approval_state: "missing",
  planner_mode: "deterministic",
};

/** Screen 4 runs with governance switched off; screen 6 runs the full control. */
const UNGOVERNED_OPTIONS: DemoOptions = { ...defaultDemoOptions, enforcement_enabled: false };

type Field = Record<string, unknown>;
const str = (screen: DemoStoryScreen, key: string): string =>
  typeof screen[key] === "string" ? (screen[key] as string) : "";
const obj = (screen: DemoStoryScreen, key: string): Field =>
  screen[key] && typeof screen[key] === "object" ? (screen[key] as Field) : {};
const arr = <T,>(source: Field, key: string): T[] =>
  Array.isArray(source[key]) ? (source[key] as T[]) : [];

function counterFor(run: ScenarioRun, variantId: "ungoverned" | "governed", action: string): ActionCounter | undefined {
  return run.variants.find((variant) => variant.id === variantId)?.counters.find((counter) => counter.action === action);
}

/* ------------------------------------------------------------------ screens */

function MeetScreen({ screen }: { screen: DemoStoryScreen }) {
  const actor = obj(screen, "actor");
  const abilities = arr<{ name: string; sensitive: boolean }>(actor, "abilities");
  return (
    <>
      <p className="screen-lede">{str(screen, "lede")}</p>
      <div className="agent-card" data-testid="agent-card">
        <div className="agent-identity">
          <span className="agent-avatar" aria-hidden="true">RA</span>
          <strong>{String(actor.name ?? "Agent")}</strong>
        </div>
        <ul className="agent-abilities">
          {abilities.map((ability) => (
            <li key={ability.name} className={ability.sensitive ? "is-sensitive" : ""}>
              <span aria-hidden="true">{ability.sensitive ? "!" : "✓"}</span>
              {ability.name}
              {ability.sensitive ? <small>leaves your building</small> : null}
            </li>
          ))}
        </ul>
      </div>
      <p className="screen-body">{str(screen, "body")}</p>
      <p className="screen-punchline">{str(screen, "punchline")}</p>
    </>
  );
}

function PageScreen({ screen }: { screen: DemoStoryScreen }) {
  const page = obj(screen, "page");
  return (
    <>
      <p className="screen-lede">{str(screen, "lede")}</p>
      <div className="fake-page" data-testid="malicious-page">
        <div className="fake-page-bar">
          <span aria-hidden="true">●●●</span>
          <code>{String(page.url ?? "")}</code>
        </div>
        <div className="fake-page-body">
          {arr<string>(page, "visible").map((line) => (
            <p key={line}>{line}</p>
          ))}
          <p className="fake-page-hidden" data-testid="hidden-instruction">
            {String(page.hidden ?? "")}
          </p>
        </div>
      </div>
      <p className="screen-body">{str(screen, "body")}</p>
      <p className="screen-punchline">{str(screen, "punchline")}</p>
    </>
  );
}

function RunScreen({
  screen,
  run,
  loading,
  error,
  onRun,
  onRetry,
}: {
  screen: DemoStoryScreen;
  run: ScenarioRun | null;
  loading: boolean;
  error: string | null;
  onRun: () => void;
  onRetry: () => void;
}) {
  const variant = (screen.variant as "ungoverned" | "governed") ?? "governed";
  const observe = obj(screen, "observe");
  const focus = String(observe.focus ?? "publish_external");
  const rules = arr<{ text: string; allowed: boolean }>(screen, "rules");
  const counter = run ? counterFor(run, variant, focus) : undefined;

  return (
    <>
      <p className="screen-lede">{str(screen, "lede")}</p>

      {rules.length ? (
        <div className="rule-card" data-testid="governance-rules">
          <p className="eyebrow">The rules we are adding</p>
          <ul>
            {rules.map((rule) => (
              <li key={rule.text} className={rule.allowed ? "rule-allow" : "rule-deny"}>
                <span aria-hidden="true">{rule.allowed ? "✓" : "⊘"}</span>
                The research agent {rule.text}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Rendered before the run, not alongside the result. The learner should
          know what the two numbers mean before watching them appear, otherwise
          the observation lands as notation to decode rather than as an answer. */}
      <WhatAmILookingAt testId="what-am-i-counters">
        {String(observe.explain_before_counters ?? "These two numbers tell us whether software actually reached and completed the sensitive function.")}
      </WhatAmILookingAt>

      {!run ? (
        <div className="screen-run">
          <button className="button button-accent button-large" type="button" disabled={loading} onClick={onRun}>
            {loading ? <><span className="button-spinner" aria-hidden="true" /> Running…</> : str(screen, "action_label")}
          </button>
          <p className="screen-safety">The publishing tool is inert. Nothing leaves this machine.</p>
        </div>
      ) : null}

      {error ? <ErrorNotice title="The run did not complete" message={error} onRetry={onRetry} /> : null}

      {run && counter ? (
        <div className="screen-observation" data-testid={`observation-${variant}`}>
          <div className="focus-counter" data-testid={`focus-counter-${variant}`}>
            <CounterCard counter={counter} />
          </div>
          <p className="screen-body">{str(screen, "body")}</p>
          <p className="screen-punchline">{str(screen, "punchline")}</p>
        </div>
      ) : null}
    </>
  );
}

function ChooseScreen({
  screen,
  picked,
  onPick,
}: {
  screen: DemoStoryScreen;
  picked: string | null;
  onPick: (optionId: string, correct: boolean) => void;
}) {
  const options = arr<{ id: string; label: string; correct: boolean; feedback: string }>(screen, "chain");
  const concept = obj(screen, "concept");
  const chosen = options.find((option) => option.id === picked);

  return (
    <>
      <p className="screen-lede">{str(screen, "lede")}</p>
      <div className="gap-chain" data-testid="gap-chain">
        <div className="gap-fixed">Agent</div>
        <div className="gap-options">
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              className={`gap-option${picked === option.id ? " is-picked" : ""}${picked && option.correct ? " is-correct" : ""}`}
              aria-pressed={picked === option.id}
              onClick={() => onPick(option.id, option.correct)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="gap-fixed">Publish tool</div>
      </div>
      {chosen ? (
        <p className={chosen.correct ? "gap-feedback is-correct" : "gap-feedback"} role="status" data-testid="gap-feedback">
          {chosen.feedback}
        </p>
      ) : null}
      {chosen?.correct ? (
        <div className="gap-reveal" data-testid="gap-reveal">
          <p className="screen-punchline">{str(screen, "reveal")}</p>
          <p className="concept-formal">
            <strong>{String(concept.plain_name ?? "")}</strong>
            <small>Technical term: {String(concept.formal_term ?? "")}</small>
          </p>
        </div>
      ) : null}
    </>
  );
}

function PositionScreen({ screen }: { screen: DemoStoryScreen }) {
  const without = obj(screen, "without");
  const withNornyx = obj(screen, "with");
  return (
    <>
      <div className="position-compare">
        <article data-testid="position-without">
          <h3>{String(without.title ?? "")}</h3>
          <ol className="layer-stack">
            {arr<string>(without, "layers").map((layer) => (
              <li key={layer}>{layer}</li>
            ))}
          </ol>
          <p className="position-problem">{String(without.problem ?? "")}</p>
        </article>
        <article data-testid="position-with">
          <h3>{String(withNornyx.title ?? "")}</h3>
          <ol className="layer-stack is-nornyx">
            {arr<string>(withNornyx, "layers").map((layer) => (
              <li key={layer}>{layer}</li>
            ))}
          </ol>
        </article>
      </div>
      <p className="position-boundary" data-testid="nornyx-boundary">
        {str(screen, "boundary")}
      </p>
    </>
  );
}

function ProofScreen({ screen }: { screen: DemoStoryScreen }) {
  const options = arr<{ id: string; label: string; strong: boolean; why: string }>(screen, "options");
  const [picked, setPicked] = useState<string | null>(null);
  const chosen = options.find((option) => option.id === picked);
  return (
    <>
      <p className="screen-lede">{str(screen, "lede")}</p>
      <div className="proof-options" data-testid="proof-options">
        {options.map((option) => (
          <button
            key={option.id}
            type="button"
            className={`proof-option${picked === option.id ? " is-picked" : ""}${picked && option.strong ? " is-strong" : ""}`}
            aria-pressed={picked === option.id}
            onClick={() => setPicked(option.id)}
          >
            {option.label}
          </button>
        ))}
      </div>
      {chosen ? (
        <p className={chosen.strong ? "proof-feedback is-strong" : "proof-feedback"} role="status" data-testid="proof-feedback">
          {chosen.why}
        </p>
      ) : null}
      {picked ? <p className="screen-punchline">{str(screen, "reveal")}</p> : null}
    </>
  );
}

function LimitsScreen({ screen, run }: { screen: DemoStoryScreen; run: ScenarioRun | null }) {
  const tier = obj(screen, "tier");
  return (
    <>
      <div className="limits-grid">
        <article className="limits-proved" data-testid="limits-proved">
          <h3>{str(screen, "proved_title")}</h3>
          {/* Taken from the run, not authored: the claim must match what happened. */}
          <p>{run?.explanation?.proves ?? run?.strongest_claim ?? "Run the demonstration to see what it supports."}</p>
        </article>
        <article className="limits-not-proved" data-testid="limits-not-proved">
          <h3>{str(screen, "not_proved_title")}</h3>
          <ul>
            {arr<string>(screen as unknown as Field, "not_proved").map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
      </div>
      <section className="tier-panel" data-testid="tier-panel">
        <p className="eyebrow">Which puts this at</p>
        <h3>{String(tier.name ?? "")}</h3>
        <p>{String(tier.body ?? "")}</p>
        <p className="tier-contrast">{String(tier.contrast ?? "")}</p>
      </section>
    </>
  );
}

/* -------------------------------------------------------------------- page */

export function DemoPage() {
  const { catalog, setLastRun, refreshProgress } = useAcademy();
  const { explore } = useMode();
  const task = useAsyncTask<ScenarioRun>();

  const [story, setStory] = useState<DemoStory | null>(null);
  const [glossary, setGlossary] = useState<GlossaryTerm[]>([]);
  const [storyError, setStoryError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [prediction, setPrediction] = useState<string | null>(null);
  // Lifted out of ChooseScreen so the answer survives Back navigation and can
  // gate progress. `gapFound` is only true for the correct choice.
  const [gapPick, setGapPick] = useState<string | null>(null);
  const [gapFound, setGapFound] = useState(false);
  const [ungovernedRun, setUngovernedRun] = useState<ScenarioRun | null>(null);
  const [governedRun, setGovernedRun] = useState<ScenarioRun | null>(null);

  useEffect(() => {
    let active = true;
    academyApi
      .demoStory()
      .then((value) => active && setStory(value))
      .catch((cause) => active && setStoryError(toErrorMessage(cause)));
    // The glossary is a reading aid for the reveal below; failing to load it
    // must not break the demonstration itself.
    academyApi
      .glossary()
      .then((value) => active && setGlossary(value.terms))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const screens = story?.screens ?? [];
  const screen = screens[index];
  const governedResult = governedRun;

  const assessmentId = useMemo(() => {
    if (!catalog) return null;
    return catalog.modules.find((module) => module.id === "F0")?.completion.assessment_id ?? null;
  }, [catalog]);

  const runVariant = useCallback(
    async (variant: "ungoverned" | "governed") => {
      const options = variant === "ungoverned" ? UNGOVERNED_OPTIONS : defaultDemoOptions;
      const run = await task.run(() => academyApi.runDemo(options));
      if (!run) return;
      if (variant === "ungoverned") setUngovernedRun(run);
      else {
        setGovernedRun(run);
        setLastRun(run);
      }
      await refreshProgress().catch(() => undefined);
    },
    [refreshProgress, setLastRun, task],
  );

  if (storyError) {
    return (
      <div className="page">
        <ErrorNotice title="The guided demonstration could not be loaded" message={storyError} />
      </div>
    );
  }
  if (!story || !screen) {
    return (
      <div className="page">
        <LoadingState label="Loading the demonstration…" />
      </div>
    );
  }

  const revealIds = arr<string>(screen as unknown as Field, "reveal_after");
  const revealedTerms = revealIds
    .map((id) => glossary.find((term) => term.id === id))
    .filter(Boolean) as GlossaryTerm[];

  const runForScreen = screen.variant === "ungoverned" ? ungovernedRun : governedRun;

  /**
   * A screen is complete when the learner has actually done the thing it exists
   * for. Rendering the steps in order is not the same as teaching in order: if
   * a learner can skip the prediction, the result violates no expectation, and
   * if they can skip the runs, the reveal explains something they never saw.
   *
   * Story, position, proof and limits screens are reading, so they are complete
   * on arrival.
   */
  function screenComplete(item: DemoStoryScreen): boolean {
    switch (item.kind) {
      case "predict":
        return prediction !== null;
      case "choose":
        return gapFound;
      case "run":
        return Boolean(item.variant === "ungoverned" ? ungovernedRun : governedRun);
      default:
        return true;
    }
  }

  // The furthest screen the learner has earned. Everything up to and including
  // it stays navigable so earlier teaching can be revisited; beyond it is
  // locked rather than merely discouraged.
  const firstIncomplete = screens.findIndex((item) => !screenComplete(item));
  const unlockedThrough = firstIncomplete === -1 ? screens.length - 1 : firstIncomplete;
  const canAdvance = screenComplete(screen);
  const isLast = index === screens.length - 1;
  const blockedReason = canAdvance
    ? null
    : screen.kind === "predict"
      ? "Choose what you think will happen first. There is no wrong answer."
      : screen.kind === "choose"
        ? "Pick the point where a check would actually help."
        : "Run it first — the next step explains what you are about to see.";

  return (
    <div className="page demo-page guided-demo">
      <header className="demo-progress-header">
        <div>
          <p className="eyebrow">The five-minute proof · step {screen.number} of {screens.length}</p>
          <h1>{screen.title}</h1>
        </div>
        <ModeSwitch />
      </header>

      <ol className="demo-dots" aria-label="Progress through the demonstration">
        {screens.map((item, position) => {
          const locked = position > unlockedThrough;
          return (
            <li
              key={item.id}
              className={
                position === index ? "is-current" : locked ? "is-locked" : position < index ? "is-done" : ""
              }
            >
              <button
                type="button"
                disabled={locked}
                onClick={() => setIndex(position)}
                aria-current={position === index ? "step" : undefined}
                aria-disabled={locked || undefined}
                data-testid={`demo-dot-${position + 1}`}
              >
                {/* `sr-only` is this repository's screen-reader utility.
                    `visually-hidden` is not defined anywhere, so a span using it
                    rendered at full size: the labels were visible text, and once
                    they grew long enough they overflowed the 7px-tall dot and
                    intercepted pointer events across the page, making parts of
                    the demo unclickable for anyone using a mouse. */}
                <span className="sr-only">
                  {`Step ${position + 1}: ${item.title}`}
                  {locked ? " (locked — finish the current step first)" : ""}
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      <section className="demo-screen" data-testid={`demo-screen-${screen.id}`} aria-live="polite">
        {screen.kind === "story" && screen.id === "meet" ? <MeetScreen screen={screen} /> : null}
        {screen.kind === "story" && screen.id === "page" ? <PageScreen screen={screen} /> : null}
        {screen.kind === "predict" ? (
          <PredictionStep
            prediction={{
              prompt: String(obj(screen, "prediction").prompt ?? ""),
              options: arr<{ id: string; label: string }>(obj(screen, "prediction"), "options"),
            }}
            committed={prediction}
            onCommit={setPrediction}
          />
        ) : null}
        {screen.kind === "run" ? (
          <RunScreen
            screen={screen}
            run={runForScreen}
            loading={task.loading}
            error={task.error}
            onRun={() => void runVariant((screen.variant as "ungoverned" | "governed") ?? "governed")}
            onRetry={() => void runVariant((screen.variant as "ungoverned" | "governed") ?? "governed")}
          />
        ) : null}
        {screen.kind === "choose" ? (
          <ChooseScreen
            screen={screen}
            picked={gapPick}
            onPick={(optionId, correct) => {
              setGapPick(optionId);
              if (correct) setGapFound(true);
            }}
          />
        ) : null}
        {screen.kind === "position" ? <PositionScreen screen={screen} /> : null}
        {screen.kind === "proof" ? <ProofScreen screen={screen} /> : null}
        {screen.kind === "limits" ? <LimitsScreen screen={screen} run={governedResult} /> : null}
      </section>

      {/* The derived explanation appears once the governed run exists, and only
          after the learner has watched both outcomes. */}
      {screen.kind === "run" && screen.variant === "governed" && governedRun?.explanation ? (
        <>
          <RunExplanation explanation={governedRun.explanation} />
          {/* The vocabulary is released here and nowhere earlier. Each of these
              terms now refers to something the learner has just watched happen,
              which is the only reason they are comprehensible at all. */}
          {revealedTerms.length ? (
            <section className="concept-reveal" data-testid="concept-reveal">
              <p className="eyebrow">These all have names now</p>
              <p>
                Everything you just watched has a technical term. You do not need to memorise
                them — they are here so the words are not new when you meet them again.
              </p>
              <GlossaryStrip terms={revealedTerms} />
            </section>
          ) : null}
        </>
      ) : null}

      <nav className="demo-nav">
        <button type="button" className="button button-secondary" disabled={index === 0} onClick={() => setIndex((value) => value - 1)}>
          ← Back
        </button>
        {!isLast ? (
          <button
            type="button"
            className="button button-primary button-large"
            disabled={!canAdvance}
            aria-disabled={!canAdvance || undefined}
            aria-describedby={blockedReason ? "demo-next-blocked" : undefined}
            onClick={() => setIndex((value) => value + 1)}
            data-testid="demo-next"
          >
            {str(screen, "cta") || "Continue"} →
          </button>
        ) : null}
      </nav>

      {/* Says why the step is held, rather than leaving a dead button. */}
      {blockedReason ? (
        <p className="demo-blocked" id="demo-next-blocked" role="status" data-testid="demo-blocked-reason">
          {blockedReason}
        </p>
      ) : null}

      {screen.kind === "run" && !runForScreen ? (
        <InfoNotice title="Run it to continue" tone="info">
          <p>This step executes the real training engine. The result you see next is that response, not a recording.</p>
        </InfoNotice>
      ) : null}

      {/* Explore mode keeps the full professional surface available at all
          times — the same run object, rendered at full density. */}
      {governedRun ? (
        <ExploreOnly>
          <details className="result-disclosure explore-full" open={explore} data-testid="explore-full-result">
            <summary>Full structured result (decisions, trace, evidence, claims)</summary>
            <ScenarioResults run={governedRun} executedConfiguration={defaultDemoOptions} configurationSource="Captured with this request" />
          </details>
        </ExploreOnly>
      ) : null}

      {isLast && governedRun && assessmentId ? (
        <AssessmentPanel assessmentId={assessmentId} onComplete={async () => refreshProgress()} />
      ) : null}
    </div>
  );
}
