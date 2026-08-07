import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { academyApi, toErrorMessage } from "../api/client";
import { ErrorNotice, LoadingState } from "../components/Feedback";
import { ProgressBar } from "../components/ProgressBar";
import { StatusBadge } from "../components/StatusBadge";
import { useAcademy } from "../context/AcademyContext";

export function DashboardPage() {
  const { dashboard, catalog, booting, serviceError, resetProgress } = useAcademy();
  const [resetOpen, setResetOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const resetTriggerRef = useRef<HTMLButtonElement>(null);
  const resetDialogRef = useRef<HTMLElement>(null);
  const modulesById = new Map(catalog?.modules.map((module) => [module.id, module]) ?? []);

  useEffect(() => {
    if (!resetOpen) return;
    const dialog = resetDialogRef.current;
    if (!dialog) return;
    const focusableSelector = "button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";
    const focusFirst = requestAnimationFrame(() => dialog.querySelector<HTMLElement>(focusableSelector)?.focus());
    // Arrow const, not a hoisted `function`: a function declaration is
    // hoisted above the `if (!dialog) return;` guard, so TypeScript cannot
    // keep `dialog` narrowed to non-null inside it (TS18047).
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setResetOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...dialog.querySelectorAll<HTMLElement>(focusableSelector)];
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      cancelAnimationFrame(focusFirst);
      document.removeEventListener("keydown", handleKeyDown);
      if (resetTriggerRef.current?.isConnected) resetTriggerRef.current.focus();
    };
  }, [resetOpen]);

  async function exportRecord() {
    setBusy(true); setActionError(null);
    try {
      const report = await academyApi.exportProgress();
      const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = "nornyx-academy-progress.json"; anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) { setActionError(toErrorMessage(error)); } finally { setBusy(false); }
  }

  async function confirmReset() {
    setBusy(true); setActionError(null);
    try { await resetProgress(); setResetOpen(false); } catch (error) { setActionError(toErrorMessage(error)); } finally { setBusy(false); }
  }

  if (booting && !dashboard) return <div className="page"><LoadingState label="Loading your learner record…" /></div>;
  if (!dashboard) return <div className="page"><header className="page-header"><h1>My dashboard</h1></header><ErrorNotice message={serviceError ?? "No learner record was returned."} /></div>;
  return (
    <div className="page">
      <header className="page-header dashboard-header"><div><p className="eyebrow">Local learner record · no registration</p><h1>My dashboard</h1><p>Completion reflects scenario execution and meaningful assessments.</p></div><div className="button-row"><button type="button" className="button button-secondary" disabled={busy} onClick={() => void exportRecord()}>Export record</button><button ref={resetTriggerRef} type="button" className="button button-quiet-danger" onClick={() => setResetOpen(true)}>Reset progress</button></div></header>
      {actionError ? <ErrorNotice message={actionError} /> : null}
      <section className="dashboard-overview">
        <div className="completion-ring"><div><strong>{Math.round(dashboard.completion_percent)}%</strong><span>complete</span></div></div>
        <div className="dashboard-summary"><h2>{dashboard.completed_modules} of {dashboard.total_modules} modules complete</h2><ProgressBar value={dashboard.completion_percent} label="Complete curriculum" /><p>Last activity: {dashboard.last_activity ? new Date(dashboard.last_activity).toLocaleString() : "No activity yet"}</p>{dashboard.current_module_id ? <Link className="button button-primary" to={`/lessons/${encodeURIComponent(dashboard.current_module_id)}`}>Continue current module</Link> : <Link className="button button-primary" to="/curriculum">Choose the first module</Link>}</div>
        <div className="dashboard-stat-grid"><article><span>Mastered</span><strong>{dashboard.concepts_mastered.length}</strong><small>concepts</small></article><article><span>Review</span><strong>{dashboard.concepts_needing_review.length}</strong><small>concepts</small></article><article><span>Capstone</span><StatusBadge status={dashboard.capstone_status} /></article></div>
      </section>
      <section className="dashboard-columns">
        <div className="dashboard-panel"><div className="section-heading compact-heading"><div><p className="eyebrow">Module record</p><h2>Recent learning</h2></div></div>{dashboard.modules.length ? <div className="record-list">{dashboard.modules.slice().sort((a, b) => (b.last_activity ?? "").localeCompare(a.last_activity ?? "")).map((record) => <article key={record.module_id} data-testid={`progress-module-${record.module_id}`}><div><h3>{modulesById.get(record.module_id)?.title ?? record.module_id}</h3><p>{record.executions} execution{record.executions === 1 ? "" : "s"} · {record.assessment_attempts} assessment attempt{record.assessment_attempts === 1 ? "" : "s"}</p></div><StatusBadge status={record.status} /><Link className="text-link" to={`/lessons/${encodeURIComponent(record.module_id)}`}>Open →</Link></article>)}</div> : <p className="muted">Your first execution or assessment will appear here.</p>}</div>
        <div className="dashboard-panel"><div className="section-heading compact-heading"><div><p className="eyebrow">Adaptive review</p><h2>Concept signals</h2></div></div><h3>Mastered</h3><div className="concept-line">{dashboard.concepts_mastered.length ? dashboard.concepts_mastered.map((concept) => <span key={concept}>{concept}</span>) : <span>No mastery evidence yet</span>}</div><h3>Needs review</h3><div className="concept-line concept-review">{dashboard.concepts_needing_review.length ? dashboard.concepts_needing_review.map((concept) => <span key={concept}>{concept}</span>) : <span>No review signals yet</span>}</div></div>
      </section>
      {resetOpen ? <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setResetOpen(false); }}><section ref={resetDialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby="reset-title" aria-describedby="reset-description" tabIndex={-1}><p className="eyebrow">Destructive local action</p><h2 id="reset-title">Reset all academy progress?</h2><p id="reset-description">This clears executions, scores, concept signals, and capstone status from the local learner record. Export first if you need a copy.</p><div className="button-row"><button type="button" className="button button-secondary" onClick={() => setResetOpen(false)}>Keep my progress</button><button type="button" className="button button-danger" disabled={busy} onClick={() => void confirmReset()}>{busy ? "Resetting…" : "Reset everything"}</button></div></section></div> : null}
    </div>
  );
}
