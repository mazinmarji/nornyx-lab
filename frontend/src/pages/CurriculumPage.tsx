import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ErrorNotice, LoadingState } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { useAcademy } from "../context/AcademyContext";

export function CurriculumPage() {
  const { catalog, dashboard, booting, serviceError } = useAcademy();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const pathId = params.get("path") ?? "all";
  const difficulty = params.get("difficulty") ?? "all";
  const selectedPath = catalog?.paths.find((path) => path.id === pathId);
  const progressByModule = new Map(dashboard?.modules.map((item) => [item.module_id, item]) ?? []);
  const modules = useMemo(() => {
    const allowed = selectedPath ? new Set(selectedPath.module_ids) : null;
    return (catalog?.modules ?? []).filter((module) => {
      if (allowed && !allowed.has(module.id)) return false;
      if (difficulty !== "all" && module.difficulty !== difficulty) return false;
      const haystack = `${module.title} ${module.summary} ${module.concepts.join(" ")}`.toLowerCase();
      return haystack.includes(query.toLowerCase());
    });
  }, [catalog, difficulty, query, selectedPath]);

  if (booting && !catalog) return <div className="page"><LoadingState label="Loading curriculum…" /></div>;
  return (
    <div className="page">
      <header className="page-header curriculum-header">
        <div><p className="eyebrow">AI engineering → agent systems → governance → Nornyx</p><h1>Curriculum</h1><p>Foundations precede controls. Each completion represents an executable check or a scored assessment—not a page view.</p></div>
        <div className="catalog-version">Catalog <strong>{catalog?.version ?? "unavailable"}</strong></div>
      </header>
      {serviceError && !catalog ? <ErrorNotice message={serviceError} /> : null}
      <section className="filter-bar" aria-label="Curriculum filters">
        <label className="search-field"><span>Search modules</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Try evidence, agents, approvals…" /></label>
        <label><span>Learning path</span><select value={pathId} onChange={(event) => { const next = new URLSearchParams(params); event.target.value === "all" ? next.delete("path") : next.set("path", event.target.value); setParams(next); }}><option value="all">Complete curriculum</option>{catalog?.paths.map((path) => <option value={path.id} key={path.id}>{path.title}</option>)}</select></label>
        <label><span>Difficulty</span><select value={difficulty} onChange={(event) => { const next = new URLSearchParams(params); event.target.value === "all" ? next.delete("difficulty") : next.set("difficulty", event.target.value); setParams(next); }}><option value="all">All levels</option><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select></label>
      </section>
      {selectedPath ? <section className="path-summary"><div><p className="eyebrow">Selected path · {selectedPath.audience}</p><h2>{selectedPath.title}</h2><p>{selectedPath.summary}</p></div><span>{selectedPath.module_ids.length} modules · {selectedPath.estimated_minutes} min</span></section> : null}
      <p className="result-count" aria-live="polite">Showing {modules.length} module{modules.length === 1 ? "" : "s"}</p>
      <div className="module-list">
        {modules.map((module, index) => {
          const record = progressByModule.get(module.id);
          const status = record?.status ?? module.status;
          return (
            <article className="module-row" key={module.id}>
              <span className="module-number">{String(index + 1).padStart(2, "0")}</span>
              <div className="module-main"><div className="module-meta"><span>{module.eyebrow}</span><span>{module.difficulty}</span><span>{module.minutes} min</span></div><h2><Link to={`/lessons/${encodeURIComponent(module.id)}`}>{module.title}</Link></h2><p>{module.summary}</p><div className="concept-line">{module.concepts.slice(0, 5).map((concept) => <span key={concept}>{concept}</span>)}</div></div>
              <div className="module-status"><StatusBadge status={status} />{record?.best_score != null ? <span>Best {Math.round(record.best_score * 100)}%</span> : null}<Link className="text-link" to={`/lessons/${encodeURIComponent(module.id)}`}>{status === "not_started" ? "Start" : "Open"} →</Link></div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

