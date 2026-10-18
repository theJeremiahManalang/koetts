type LoadingStateProps = { label?: string; compact?: boolean };

export function LoadingState({ label = "Preparing your reading space…", compact = false }: LoadingStateProps) {
  return <div className={compact ? "loading-status" : "loading-screen"} role="status" aria-live="polite" aria-atomic="true">
    <span className="loading-panels" aria-hidden="true"><i /><i /><i /></span>
    <div className="loading-copy"><p>{label}</p>{!compact && <span>Your manga, voices and saved work will appear here.</span>}</div>
    {!compact && <div className="loading-skeleton" aria-hidden="true"><div /><div><i /><i /><i /></div></div>}
  </div>;
}
