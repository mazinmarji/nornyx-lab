import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { academyApi, toErrorMessage } from "../api/client";
import { ErrorNotice, LoadingState } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { ExploreOnly, ModeSwitch } from "../components/Teaching";
import { useAcademy } from "../context/AcademyContext";
import type { CurriculumModule, StageMap, StageStep } from "../types";

function StepRow({
  step,
  modulesById,
}: {
  step: StageStep;
  modulesById: Map<string, CurriculumModule>;
}) {
  const modules = step.module_ids.map((id) => modulesById.get(id)).filter(Boolean) as CurriculumModule[];
  const complete = modules.length > 0 && modules.every((module) => module.status === "complete");
  const target = modules[0];

  return (
    <li className={complete ? "stage-step is-complete" : "stage-step"} data-testid={`stage-step-${step.number}`}>
      <span className="step-tick" aria-hidden="true">{complete ? "✓" : step.number}</span>
      <div className="step-body">
        {target ? (
          <Link to={`/lessons/${encodeURIComponent(target.id)}`} className="step-name">
            {step.name}
          </Link>
        ) : (
          <span className="step-name">{step.name}</span>
        )}
        <p className="step-plain">{step.plain}</p>
        <ExploreOnly>
          <p className="step-modules">
            {modules.map((module) => (
              <span key={module.id}>
                <code>{module.id}</code> {module.title}
              </span>
            ))}
          </p>
        </ExploreOnly>
      </div>
      {target ? <StatusBadge status={target.status} /> : null}
    </li>
  );
}

export function CurriculumPage() {
  const { catalog, booting, serviceError } = useAcademy();
  const [stages, setStages] = useState<StageMap | null>(null);
  const [stagesError, setStagesError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    academyApi
      .stages()
      .then((value) => active && setStages(value))
      .catch((cause) => active && setStagesError(toErrorMessage(cause)));
    return () => {
      active = false;
    };
  }, []);

  const modulesById = useMemo(
    () => new Map((catalog?.modules ?? []).map((module) => [module.id, module])),
    [catalog],
  );
  const entryModules = useMemo(
    () => (stages?.entry.module_ids ?? []).map((id) => modulesById.get(id)).filter(Boolean) as CurriculumModule[],
    [modulesById, stages],
  );

  if (booting && !catalog) return <div className="page"><LoadingState label="Loading curriculum…" /></div>;

  return (
    <div className="page curriculum-page">
      <header className="page-header curriculum-header">
        <div>
          <p className="eyebrow">Seven stages · from "what is a model" to building one yourself</p>
          <h1>The whole path</h1>
          <p>
            Each stage answers a question the previous one raised. You do not need to know any of
            the vocabulary before you start — every term is introduced at the point it becomes
            useful.
          </p>
        </div>
        <ModeSwitch />
      </header>

      {serviceError ? <ErrorNotice title="The academy service is not connected" message={serviceError} /> : null}
      {stagesError ? <ErrorNotice title="The stage map could not be loaded" message={stagesError} /> : null}

      {/* Concept-based progress. Module counts stay available but subordinate:
          "7/31 modules" tells a learner nothing about what they understand. */}
      {stages ? (
        <section className="concept-progress" data-testid="concept-progress">
          <div>
            <p className="eyebrow">You understand</p>
            {stages.understood_concepts.length ? (
              <ul className="understood-list">
                {stages.understood_concepts.map((concept) => (
                  <li key={concept}>
                    <span aria-hidden="true">✓</span>
                    {concept}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">Nothing yet — that is exactly where everyone starts.</p>
            )}
          </div>
          <div>
            <p className="eyebrow">Next</p>
            <ul className="next-list">
              {stages.next_concepts.map((concept) => (
                <li key={concept}>
                  <span aria-hidden="true">→</span>
                  {concept}
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      {stages && entryModules.length ? (
        <section className="stage-entry" data-testid="stage-entry">
          <p className="eyebrow">Before stage 1</p>
          <div className="stage-entry-body">
            <div>
              <h2>{entryModules[0].title}</h2>
              <p>Watch the whole problem happen once, before learning any of the parts.</p>
            </div>
            <Link className="button button-accent" to="/demo">Open the demonstration →</Link>
          </div>
        </section>
      ) : null}

      {!stages && !stagesError ? <LoadingState label="Loading the stages…" /> : null}

      <div className="stage-list">
        {stages?.stages.map((stage) => (
          <section key={stage.id} className="stage-card" data-testid={`stage-${stage.number}`}>
            <header className="stage-head">
              <div>
                <p className="eyebrow">Stage {stage.number}</p>
                <h2>{stage.name}</h2>
                <p className="stage-question">{stage.question}</p>
                <p className="stage-plain">{stage.plain}</p>
              </div>
              <div className="stage-count" aria-label={`${stage.completed_steps} of ${stage.total_steps} understood`}>
                <strong>{stage.completed_steps}</strong>
                <span>of {stage.total_steps}</span>
              </div>
            </header>
            <ol className="stage-steps">
              {stage.steps.map((step) => (
                <StepRow key={step.number} step={step} modulesById={modulesById} />
              ))}
            </ol>
          </section>
        ))}
      </div>

      <ExploreOnly>
        <section className="catalog-meta">
          <p className="eyebrow">Engineering detail</p>
          <p>
            Catalog version <strong>{catalog?.version ?? "unavailable"}</strong> ·{" "}
            {catalog?.modules.length ?? 0} modules · the identifiers above (F0–F5, 00–24) are the
            repository's own, retained for deep links and the migration matrix.
          </p>
          <Link className="text-link" to="/paths">Audience-based learning paths →</Link>
        </section>
      </ExploreOnly>
    </div>
  );
}
