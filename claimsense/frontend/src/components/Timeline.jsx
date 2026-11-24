import { STAGES, errorText, ms } from "../format.js";

/** Horizontal stage timeline: bar position = start offset, width = duration. */
export default function Timeline({ events }) {
  if (!events?.length) return <p className="muted">No stage events recorded.</p>;
  const starts = events.map((e) => new Date(e.started_at).getTime());
  const t0 = Math.min(...starts);
  const end = Math.max(...events.map((e, i) => starts[i] + e.duration_ms));
  const span = Math.max(end - t0, 1);
  return (
    <div className="timeline">
      {events.map((e, i) => {
        const left = ((starts[i] - t0) / span) * 100;
        const width = (e.duration_ms / span) * 100;
        return (
          <div className="tl-row" key={i}>
            <div className={`tl-label ${e.status}`}>
              {STAGES[e.span_name] || e.span_name}
              {e.error_category && <div className="small">{errorText(e.error_category)}</div>}
            </div>
            <div className="tl-track" title={`${e.span_name}: ${e.duration_ms} ms`}>
              <div className={`tl-bar ${e.status}`} style={{ left: `${left}%`, width: `${width}%` }} />
            </div>
            <div className="num small right">{ms(e.duration_ms)}</div>
          </div>
        );
      })}
    </div>
  );
}
