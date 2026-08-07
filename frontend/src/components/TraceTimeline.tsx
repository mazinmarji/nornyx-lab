import type { TraceEvent } from "../types";

export function TraceTimeline({ trace, title = "Ordered execution trace" }: { trace: TraceEvent[]; title?: string }) {
  const ordered = [...trace].sort((a, b) => a.sequence - b.sequence);
  return (
    <section className="trace-panel" aria-labelledby={`trace-${title.replaceAll(" ", "-")}`}>
      <div className="section-heading compact-heading">
        <div>
          <p className="eyebrow">Observed sequence</p>
          <h3 id={`trace-${title.replaceAll(" ", "-")}`}>{title}</h3>
        </div>
        <span className="quiet-count">{ordered.length} events</span>
      </div>
      {ordered.length ? (
        <ol className="timeline">
          {ordered.map((event) => (
            <li key={`${event.sequence}-${event.event_type}`} className={`timeline-${event.phase}`}>
              <span className="timeline-index">{event.sequence}</span>
              <div>
                <div className="timeline-topline">
                  <span>{event.phase}</span>
                  <code>{event.event_type}</code>
                </div>
                <h4>{event.title}</h4>
                <p>{event.detail}</p>
                {Object.keys(event.fields).length ? (
                  <dl className="field-list field-list-inline">
                    {Object.entries(event.fields).map(([key, fieldValue]) => (
                      <div key={key}>
                        <dt>{key.replaceAll("_", " ")}</dt>
                        <dd>{typeof fieldValue === "string" ? fieldValue : JSON.stringify(fieldValue)}</dd>
                      </div>
                    ))}
                  </dl>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">No trace events were returned.</p>
      )}
    </section>
  );
}

