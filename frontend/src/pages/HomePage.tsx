import { Link } from "react-router-dom";
import { AssistantAgentDiagram } from "../components/Diagrams";
import { ErrorNotice } from "../components/Feedback";
import { ProgressBar } from "../components/ProgressBar";
import { useAcademy } from "../context/AcademyContext";

export function HomePage() {
  const { dashboard, serviceError } = useAcademy();
  const continueTarget = dashboard?.current_module_id
    ? `/lessons/${encodeURIComponent(dashboard.current_module_id)}`
    : "/curriculum";
  return (
    <div className="page home-page">
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Interactive academy · no account or API key required</p>
          <h1>Build AI agents that can act.<br /><span>Govern what happens next.</span></h1>
          <p className="hero-lede">
            Learn AI software, agent tools, policy, runtime controls, evidence, and honest assurance—from a first assistant to a governed multi-agent system.
          </p>
          <div className="button-row">
            <Link className="button button-primary button-large" to="/curriculum">Start from the beginning</Link>
            <Link className="button button-accent button-large" to="/demo">Run the five-minute demo</Link>
          </div>
          <div className="hero-proof" aria-label="Platform characteristics">
            <span><strong>25</strong> original labs migrated</span>
            <span><strong>Offline</strong> deterministic default</span>
            <span><strong>Inert</strong> business effects</span>
          </div>
        </div>
        <div className="hero-panel" aria-label="A governance decision at a glance">
          <div className="hero-panel-top"><span>atlas.publish_external</span><span className="live-dot">Awaiting API run</span></div>
          <div className="hero-agent-row"><span className="agent-avatar">RA</span><div><strong>Research agent</strong><small>untrusted.web → public.internet</small></div></div>
          <div className="hero-decision"><span aria-hidden="true">?</span><div><strong>What will the control path decide?</strong><small>Run the demo to load policy, gate, approval, and enforcement data.</small></div></div>
          <div className="hero-counters"><div><strong>?</strong><small>attempts</small></div><div><strong>?</strong><small>completions</small></div></div>
          <p className="hero-panel-note">Navigation preview only. No governance outcome is shown until the academy API returns one.</p>
        </div>
      </section>

      {serviceError ? <ErrorNotice title="The local academy service is not connected" message={`${serviceError} Navigation remains available, but executable results and progress require the service.`} /> : null}

      <section className="orientation-section">
        <div className="section-heading wide-heading">
          <div><p className="eyebrow">Start with the essential distinction</p><h2>An assistant suggests. An agent can create a side effect.</h2></div>
          <p>Once software can call a tool, send, publish, transfer, or modify, a confident message is not proof that the action was prevented.</p>
        </div>
        <AssistantAgentDiagram />
        <div className="definition-grid">
          <article><span className="definition-number">01</span><h3>Plan</h3><p>A model or deterministic planner proposes an action. Proposed work is not completed work.</p></article>
          <article><span className="definition-number">02</span><h3>Decide</h3><p>Identity, capability, resource, zone, policy, gate, and approval determine authorization.</p></article>
          <article><span className="definition-number">03</span><h3>Enforce</h3><p>A decision matters only where an enforcement point controls the path to the tool.</p></article>
          <article><span className="definition-number">04</span><h3>Evidence</h3><p>Counters and bound events support a scoped claim—not a claim about unobserved paths.</p></article>
        </div>
      </section>

      <section className="start-grid" aria-labelledby="choose-start-heading">
        <div className="section-heading"><div><p className="eyebrow">Choose your entry point</p><h2 id="choose-start-heading">Learn, compare, or inspect</h2></div></div>
        <div className="action-card-grid">
          <Link className="action-card featured-card" to="/demo"><span>5 min</span><h3>Compare governed and ungoverned behavior</h3><p>Run the same publish plan twice and inspect why the tool counters differ.</p><strong>Open the demonstration →</strong></Link>
          <Link className="action-card" to="/paths"><span>7 paths</span><h3>Choose for your role</h3><p>Beginner, developer, agent engineer, architect, governance, or Nornyx practitioner.</p><strong>Explore learning paths →</strong></Link>
          <Link className="action-card" to={continueTarget}><span>Local record</span><h3>Continue your progress</h3>{dashboard ? <ProgressBar value={dashboard.completion_percent} label={`${dashboard.completed_modules} of ${dashboard.total_modules} modules`} /> : <p>Your learner record appears here when the service connects.</p>}<strong>Continue learning →</strong></Link>
          <Link className="action-card" to="/contracts"><span>Advanced inspection</span><h3>Explore real contracts</h3><p>Move between graph, authoritative source, generated controls, and diagnostics.</p><strong>Open contract explorer →</strong></Link>
        </div>
      </section>

      <section className="nornyx-position">
        <div><p className="eyebrow">Where Nornyx fits</p><h2>Governance contracts and controls around your agent system</h2></div>
        <p>Nornyx declares, checks, composes, generates, locks, decides, and validates supplied evidence. Your model, framework, application, identity system, enforcement surface, and tool runtime still have distinct responsibilities.</p>
        <Link className="text-link light-link" to="/about">Read the honest boundaries →</Link>
      </section>
    </div>
  );
}
