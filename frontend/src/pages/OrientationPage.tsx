import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { academyApi, toErrorMessage } from "../api/client";
import { ErrorNotice, LoadingState } from "../components/Feedback";
import { OrientationDiagram } from "../components/Diagrams";
import type { Orientation, OrientationIdea } from "../types";

function IdeaCard({ idea }: { idea: OrientationIdea }) {
  return (
    <article className={`orientation-idea idea-${idea.id}`} data-testid={`orientation-idea-${idea.id}`}>
      <header>
        <span className="idea-number" aria-hidden="true">
          {idea.number}
        </span>
        <div>
          <p className="eyebrow">{idea.name}</p>
          <h2>{idea.headline}</h2>
        </div>
      </header>
      <p className="idea-body">{idea.body}</p>

      <OrientationDiagram kind={idea.diagram} />

      {idea.example_prompt ? (
        <div className="idea-example">
          <div>
            <span>You give it</span>
            <code>{idea.example_prompt}</code>
          </div>
          <div>
            <span>You get</span>
            <p>{idea.example_output}</p>
          </div>
        </div>
      ) : null}

      {idea.questions.length ? (
        <ul className="idea-questions">
          {idea.questions.map((question) => (
            <li key={question}>{question}</li>
          ))}
        </ul>
      ) : null}

      <p className="idea-punchline">{idea.punchline}</p>
    </article>
  );
}

export function OrientationPage() {
  const [orientation, setOrientation] = useState<Orientation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    academyApi
      .orientation()
      .then((value) => active && setOrientation(value))
      .catch((cause) => active && setError(toErrorMessage(cause)));
    return () => {
      active = false;
    };
  }, []);

  if (error) return <div className="page"><ErrorNotice title="The orientation could not be loaded" message={error} /></div>;
  if (!orientation) return <div className="page"><LoadingState label="Loading orientation…" /></div>;

  return (
    <div className="page orientation-page">
      <header className="orientation-header">
        <p className="eyebrow">Start here · {orientation.minutes} minutes · nothing to install</p>
        <h1>{orientation.title}</h1>
        <p className="orientation-subtitle">{orientation.subtitle}</p>
        <p className="orientation-lede">{orientation.lede}</p>
      </header>

      <div className="orientation-ideas">
        {orientation.ideas.map((idea) => (
          <IdeaCard key={idea.id} idea={idea} />
        ))}
      </div>

      <section className="orientation-nornyx">
        <p className="eyebrow">One more thing</p>
        <h2>{orientation.nornyx_position.headline}</h2>
        <p>{orientation.nornyx_position.body}</p>
        <p className="orientation-boundary">{orientation.nornyx_position.boundary}</p>
      </section>

      <section className="orientation-closing">
        <h2>{orientation.closing.headline}</h2>
        <p>{orientation.closing.body}</p>
        <Link className="button button-accent button-large" to="/demo">
          {orientation.closing.cta} →
        </Link>
      </section>
    </div>
  );
}
