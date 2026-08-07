import { Link } from "react-router-dom";
import { ErrorNotice, LoadingState } from "../components/Feedback";
import { ProgressBar } from "../components/ProgressBar";
import { useAcademy } from "../context/AcademyContext";

export function PathsPage() {
  const { catalog, booting, serviceError } = useAcademy();
  if (booting && !catalog) return <div className="page"><LoadingState label="Loading learning paths…" /></div>;
  return (
    <div className="page">
      <header className="page-header">
        <p className="eyebrow">Audience-aware routes through one curriculum</p>
        <h1>Choose a learning path</h1>
        <p>Every path names its prerequisites, effort, outcomes, and completion rule. You can switch paths without losing local progress.</p>
      </header>
      {serviceError && !catalog ? <ErrorNotice message={serviceError} /> : null}
      <div className="path-grid">
        {catalog?.paths.map((path, index) => {
          const percent = path.total_modules ? (path.completed_modules / path.total_modules) * 100 : 0;
          return (
            <article className={`path-card${index === 0 ? " path-card-featured" : ""}`} key={path.id}>
              <div className="path-card-top"><span className="path-index">{String(index + 1).padStart(2, "0")}</span><span>{Math.round(path.estimated_minutes / 60 * 10) / 10} hours</span></div>
              <p className="eyebrow">{path.audience}</p>
              <h2>{path.title}</h2>
              <p>{path.summary}</p>
              <ProgressBar value={percent} label={`${path.completed_modules} of ${path.total_modules} complete`} />
              <dl className="path-details"><div><dt>Prerequisites</dt><dd>{path.prerequisites.length ? path.prerequisites.join(" · ") : "None"}</dd></div><div><dt>Concepts</dt><dd>{path.concepts.slice(0, 5).join(" · ")}</dd></div></dl>
              <details><summary>Expected outcomes and completion</summary><ul>{path.outcomes.map((outcome) => <li key={outcome}>{outcome}</li>)}</ul><p><strong>Complete when:</strong> {path.completion_criteria}</p></details>
              <Link className="button button-secondary" to={`/curriculum?path=${encodeURIComponent(path.id)}`}>View this path</Link>
            </article>
          );
        })}
      </div>
    </div>
  );
}

