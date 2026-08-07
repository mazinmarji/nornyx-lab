import { useEffect, useMemo, useState } from "react";
import { academyApi, toErrorMessage } from "../api/client";
import { ErrorNotice, LoadingState } from "../components/Feedback";
import { ExploreOnly, ModeSwitch } from "../components/Teaching";
import type { Glossary, GlossaryTerm } from "../types";

const STAGE_NAMES: Record<number, string> = {
  1: "Understand AI",
  2: "From AI to agents",
  3: "The governance problem",
  4: "Proving what happened",
  5: "Nornyx",
  6: "Frameworks",
  7: "Building it",
};

function TermCard({ term }: { term: GlossaryTerm }) {
  return (
    <article className="glossary-card" id={`term-${term.id}`} data-testid={`glossary-term-${term.id}`}>
      <header>
        <h2>{term.term}</h2>
        {term.also.length ? <p className="glossary-also">Also called: {term.also.join(", ")}</p> : null}
      </header>
      <p className="glossary-plain">{term.plain}</p>
      <dl>
        <div>
          <dt>Why it matters</dt>
          <dd>{term.why}</dd>
        </div>
        <div>
          <dt>Example</dt>
          <dd>{term.example}</dd>
        </div>
        <div>
          <dt>In Nornyx</dt>
          <dd>{term.nornyx}</dd>
        </div>
      </dl>
      <ExploreOnly>
        <p className="glossary-formal">
          <span>Formally</span> {term.formal}
        </p>
      </ExploreOnly>
    </article>
  );
}

export function GlossaryPage() {
  const [glossary, setGlossary] = useState<Glossary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let active = true;
    academyApi
      .glossary()
      .then((value) => active && setGlossary(value))
      .catch((cause) => active && setError(toErrorMessage(cause)));
    return () => {
      active = false;
    };
  }, []);

  const grouped = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matching = (glossary?.terms ?? []).filter(
      (term) =>
        !needle ||
        term.term.toLowerCase().includes(needle) ||
        term.plain.toLowerCase().includes(needle) ||
        term.also.some((name) => name.toLowerCase().includes(needle)),
    );
    const buckets = new Map<number, GlossaryTerm[]>();
    for (const term of matching) {
      buckets.set(term.stage, [...(buckets.get(term.stage) ?? []), term]);
    }
    return [...buckets.entries()].sort(([left], [right]) => left - right);
  }, [glossary, query]);

  if (error) return <div className="page"><ErrorNotice title="The glossary could not be loaded" message={error} /></div>;
  if (!glossary) return <div className="page"><LoadingState label="Loading glossary…" /></div>;

  return (
    <div className="page glossary-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Plain language first</p>
          <h1>What the words mean</h1>
          <p>
            You should never need this page to follow a lesson — every term is explained where it is
            first used. This is here for when you want to look one up again.
          </p>
        </div>
        <ModeSwitch />
      </header>

      <label className="glossary-search">
        <span>Find a term</span>
        <input
          type="search"
          value={query}
          placeholder="capability, evidence, PEP…"
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>

      {grouped.length === 0 ? <p className="muted">No term matches “{query}”.</p> : null}

      {grouped.map(([stage, terms]) => (
        <section key={stage} className="glossary-stage">
          <h2 className="glossary-stage-heading">
            <span>{stage}</span> {STAGE_NAMES[stage] ?? "Other"}
          </h2>
          <div className="glossary-grid">
            {terms.map((term) => (
              <TermCard key={term.id} term={term} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
