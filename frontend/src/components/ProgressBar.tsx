export function ProgressBar({ value, label }: { value: number; label: string }) {
  const normalized = Math.max(0, Math.min(100, value));
  return (
    <div className="progress-wrap">
      <div className="progress-label">
        <span>{label}</span>
        <strong>{Math.round(normalized)}%</strong>
      </div>
      <progress className="progress-native" aria-label={label} max={100} value={normalized}>
        {Math.round(normalized)}%
      </progress>
    </div>
  );
}
