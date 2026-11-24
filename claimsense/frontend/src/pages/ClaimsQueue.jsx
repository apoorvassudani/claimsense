import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, useApi } from "../api.js";
import { CLAIM_TYPES, RULES, STATUS, fmtDate, inr } from "../format.js";
import { RiskBadge, StatusChip } from "../components/Badges.jsx";
import { Empty, ErrorState, Loading } from "../components/States.jsx";

const RISK_ORDER = { HIGH: 0, MEDIUM: 1, LOW: 2, null: 3 };

export default function ClaimsQueue() {
  const navigate = useNavigate();
  const { data, error, loading, reload } = useApi(() => api.claims(), []);
  const [risk, setRisk] = useState("ALL");
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("risk");

  const claims = data || [];
  const counts = useMemo(() => {
    const c = { ALL: claims.length, HIGH: 0, MEDIUM: 0, LOW: 0 };
    claims.forEach((x) => x.risk_level && (c[x.risk_level] += 1));
    return c;
  }, [claims]);
  const waiting = claims.filter((c) => c.status === "NEEDS_REVIEW").length;

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = claims.filter(
      (c) =>
        (risk === "ALL" || c.risk_level === risk) &&
        (!status || c.status === status) &&
        (!type || c.claim_type === type) &&
        (!q || c.claim_number.toLowerCase().includes(q) || c.claimant_name.toLowerCase().includes(q)),
    );
    return filtered.sort((a, b) =>
      sort === "risk"
        ? RISK_ORDER[a.risk_level] - RISK_ORDER[b.risk_level] || (b.risk_score || 0) - (a.risk_score || 0) ||
          b.incident_date.localeCompare(a.incident_date)
        : b.incident_date.localeCompare(a.incident_date),
    );
  }, [claims, risk, status, type, search, sort]);

  const clear = () => { setRisk("ALL"); setStatus(""); setType(""); setSearch(""); };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Claims queue</h1>
          {data && (
            <p className="sub">
              {claims.length} claims. {waiting} waiting for a reviewer's decision.
            </p>
          )}
        </div>
        <Link className="btn primary" to="/claims/new">New claim</Link>
      </div>

      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && !data && <Loading label="Loading claims…" />}

      {data && claims.length === 0 && (
        <div className="panel">
          <Empty title="No claims yet" action={<Link className="btn primary" to="/claims/new">Create a claim</Link>}>
            Load the synthetic dataset with <span className="code">python -m app.seed</span>, or create a claim yourself.
          </Empty>
        </div>
      )}

      {claims.length > 0 && (
        <>
          <div className="toolbar">
            <div className="segmented" role="group" aria-label="Filter by risk">
              {["ALL", "HIGH", "MEDIUM", "LOW"].map((r) => (
                <button key={r} aria-pressed={risk === r} onClick={() => setRisk(r)}>
                  {r === "ALL" ? "All" : r[0] + r.slice(1).toLowerCase()} <span className="num muted">{counts[r]}</span>
                </button>
              ))}
            </div>
            <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Any status</option>
              {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select aria-label="Filter by claim type" value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">All types</option>
              {Object.entries(CLAIM_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <input className="grow" type="search" placeholder="Search by claim number or claimant"
                   aria-label="Search claims" value={search} onChange={(e) => setSearch(e.target.value)} />
            <select aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="risk">Highest risk first</option>
              <option value="date">Newest incident first</option>
            </select>
          </div>

          {rows.length === 0 ? (
            <div className="panel">
              <Empty title="No claims match these filters" action={<button className="btn" onClick={clear}>Clear filters</button>} />
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th aria-label="Risk colour" />
                    <th>Claim</th>
                    <th>Claimant</th>
                    <th>Incident</th>
                    <th className="right">Claimed</th>
                    <th>Risk</th>
                    <th>Status</th>
                    <th>Red flags</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((c) => (
                    <tr key={c.claim_id} className="clickable" onClick={() => navigate(`/claims/${c.claim_id}`)}>
                      <td className="risk-tab"><span className={c.risk_level || ""} /></td>
                      <td>
                        <Link to={`/claims/${c.claim_id}`} onClick={(e) => e.stopPropagation()}>{c.claim_number}</Link>
                        <div className="small muted">{CLAIM_TYPES[c.claim_type]}</div>
                      </td>
                      <td>{c.claimant_name}</td>
                      <td className="num">{fmtDate(c.incident_date)}</td>
                      <td className="num right">{inr(c.claimed_amount)}</td>
                      <td><RiskBadge level={c.risk_level} score={c.risk_score} /></td>
                      <td><StatusChip status={c.status} /></td>
                      <td className="flags">
                        {c.rule_codes.length === 0 ? <span className="muted">None</span>
                          : c.rule_codes.slice(0, 2).map((r) => RULES[r] || r).join("; ")}
                        {c.rule_codes.length > 2 && <span className="muted"> and {c.rule_codes.length - 2} more</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="small muted" style={{ marginTop: 10 }}>
            Showing {rows.length} of {claims.length}. Risk scores come from fixed rules; the AI only reads the documents.
          </p>
        </>
      )}
    </>
  );
}
