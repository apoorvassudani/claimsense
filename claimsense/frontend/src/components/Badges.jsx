import { STATUS } from "../format.js";

export function RiskBadge({ level, score }) {
  if (!level) return <span className="muted small">Not scored</span>;
  const label = { LOW: "Low", MEDIUM: "Medium", HIGH: "High" }[level];
  return (
    <span className={`risk ${level}`}>
      <span className="dot" aria-hidden="true" />
      {label}
      {score !== undefined && score !== null && <span className="num muted" style={{ fontWeight: 500 }}>{score}</span>}
    </span>
  );
}

export function StatusChip({ status }) {
  return <span className={`chip ${status}`}>{STATUS[status] || status}</span>;
}
