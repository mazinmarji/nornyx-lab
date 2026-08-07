import type { ReactNode } from "react";

export function LoadingState({ label = "Loading academy data…" }: { label?: string }) {
  return (
    <div className="loading-state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorNotice({
  title = "The service could not complete this request",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <section className="notice notice-error" role="alert">
      <div className="notice-mark" aria-hidden="true">!</div>
      <div>
        <h2>{title}</h2>
        <p>{message}</p>
        {onRetry ? (
          <button className="button button-secondary" type="button" onClick={onRetry}>
            Try again
          </button>
        ) : null}
      </div>
    </section>
  );
}

export function InfoNotice({
  title,
  children,
  tone = "info",
}: {
  title: string;
  children: ReactNode;
  tone?: "info" | "warning" | "success";
}) {
  return (
    <section className={`notice notice-${tone}`}>
      <div className="notice-mark" aria-hidden="true">{tone === "warning" ? "!" : "i"}</div>
      <div>
        <h2>{title}</h2>
        <div>{children}</div>
      </div>
    </section>
  );
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="empty-state">
      <div className="empty-symbol" aria-hidden="true">◇</div>
      <h2>{title}</h2>
      <div>{children}</div>
    </section>
  );
}

