export function Loading({ label = "Loading…" }) {
  return (
    <div className="state" role="status">
      <span className="spinner" /> <span style={{ marginLeft: 8 }}>{label}</span>
    </div>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="notice error" role="alert">
      <strong>{error?.status === 0 ? "Backend not reachable. " : "Something went wrong. "}</strong>
      {error?.message || String(error)}
      {error?.traceId && <div className="small muted">Trace ID: <span className="code">{error.traceId}</span></div>}
      {onRetry && (
        <div style={{ marginTop: 10 }}>
          <button className="btn" onClick={() => onRetry()}>Try again</button>
        </div>
      )}
    </div>
  );
}

export function Empty({ title, children, action }) {
  return (
    <div className="state">
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}
