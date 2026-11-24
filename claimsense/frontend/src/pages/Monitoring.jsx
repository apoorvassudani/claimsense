import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, useApi } from "../api.js";
import { errorText, fmtTime, ms } from "../format.js";
import { Empty, ErrorState, Loading } from "../components/States.jsx";
import { useClaimsIndex } from "../claimsIndex.jsx";

const WINDOWS = { "": "All time", 1: "Last hour", 24: "Last 24 hours", 168: "Last 7 days" };

export default function Monitoring() {
  const navigate = useNavigate();
  const index = useClaimsIndex();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const model = params.get("model") || "";
  const hours = params.get("hours") || "";
  const [auto, setAuto] = useState(true);
  const metrics = useApi(() => api.metrics(), [], { refreshMs: auto ? 15000 : 0 });
  const runs = useApi(() => api.runs({ status, model, hours, limit: 100 }), [status, model, hours], { refreshMs: auto ? 15000 : 0 });
  const recent = useApi(() => api.runs({ limit: 40 }), [], { refreshMs: auto ? 15000 : 0 });

  const setFilter = (k, v) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    setParams(next, { replace: true });
  };
  const claimNumber = (cid) => index.claims.find((c) => c.claim_id === cid)?.claim_number || `#${cid}`;

  if (metrics.error) return <ErrorState error={metrics.error} onRetry={metrics.reload} />;
  if (!metrics.data) return <Loading label="Loading monitoring data…" />;
  const m = metrics.data;
  const chart = [...(recent.data || [])].reverse().map((r, i) => ({ i: i + 1, ms: r.latency_ms || 0, failed: r.status === "FAILED", run: r }));
  const fb = m.feedback || { reviews: 0, helpful: 0, not_helpful: 0 };
  const rated = fb.helpful + fb.not_helpful;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Monitoring</h1>
          <p className="sub">Every AI call, how long it took, whether it failed, and what reviewers thought of the results.</p>
        </div>
        <label className="inline-choice small"><input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />Refresh every 15 seconds</label>
      </div>

      {m.alerts.map((a) => (
        <div key={a.code} className="notice error" role="alert">
          <strong>{a.code === "HIGH_FAILURE_RATE" ? "Many AI calls are failing. " : "Slow AI calls. "}</strong>
          {a.message}.{" "}
          {a.code === "HIGH_FAILURE_RATE"
            ? <button className="btn" style={{ marginLeft: 8, padding: "3px 10px" }} onClick={() => setFilter("status", "FAILED")}>Show failed calls</button>
            : a.run_ids?.[0] && <Link to={`/runs/${a.run_ids[0]}`}>Open the slowest recent call</Link>}
        </div>
      ))}

      <div className="metrics">
        <Metric label="AI calls" value={m.total_runs} note={`${m.success} succeeded`} />
        <Metric label="Error rate" value={`${(m.error_rate * 100).toFixed(1)}%`} bad={m.error_rate > 0.2}
                note={m.failed ? <button className="btn" style={{ padding: "1px 8px", fontSize: 12.5 }} onClick={() => setFilter("status", "FAILED")}>{m.failed} failed</button> : "No failures"} />
        <Metric label="p95 latency" value={ms(m.p95_latency_ms)} bad={(m.p95_latency_ms || 0) > m.slow_call_ms}
                note={`Slow-call alert above ${ms(m.slow_call_ms)}`} />
        <Metric label="Average latency" value={ms(m.avg_latency_ms)} note="Includes rate-limit waits" />
        <Metric label="Reviewer feedback" value={rated ? `${Math.round((fb.helpful / rated) * 100)}%` : "—"}
                note={rated ? `${fb.helpful} of ${rated} said the AI read correctly` : "No ratings yet"} />
      </div>

      <div className="two-col">
        <div className="panel panel-pad">
          <h2 style={{ marginBottom: 4 }}>Latest 40 AI calls</h2>
          <p className="small muted" style={{ marginBottom: 10 }}>Bar height is the time taken. Red bars failed. Select a bar to open its trace.</p>
          <div style={{ height: 220 }}>
            <ResponsiveContainer>
              <BarChart data={chart} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="#E9EDF2" />
                <XAxis dataKey="i" tick={false} axisLine={{ stroke: "#D9DEE5" }} />
                <YAxis tickFormatter={(v) => (v >= 1000 ? `${v / 1000}s` : `${v}ms`)} width={60} tick={{ fontSize: 12, fill: "#6B7686" }} axisLine={false} tickLine={false} />
                <Tooltip formatter={(v) => [ms(v), "Time"]} labelFormatter={(_, p) => (p?.[0] ? `${p[0].payload.run.status.toLowerCase()} · ${fmtTime(p[0].payload.run.created_at)}` : "")} />
                <ReferenceLine y={m.slow_call_ms} stroke="#B7791F" strokeDasharray="4 4" />
                <Bar dataKey="ms" radius={[2, 2, 0, 0]} cursor="pointer" onClick={(d) => navigate(`/runs/${d.run?.run_id || d.payload?.run?.run_id}`)}>
                  {chart.map((d) => <Cell key={d.i} fill={d.failed ? "#B42318" : "#2457A6"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="panel panel-pad">
          <h2 style={{ marginBottom: 10 }}>Failures by cause</h2>
          {Object.keys(m.errors_by_type).length === 0 ? <p className="small muted">No failures recorded.</p> : (
            <table className="kv"><tbody>
              {Object.entries(m.errors_by_type).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                <tr key={k}><td>{errorText(k)}</td><td className="num right">{v}</td></tr>
              ))}
            </tbody></table>
          )}
          <h3 className="small" style={{ margin: "16px 0 6px" }}>By model</h3>
          <table className="kv"><tbody>
            {Object.entries(m.by_model).map(([k, v]) => (
              <tr key={k}><td className="code" style={{ fontSize: 12 }}>{k}</td><td className="num right">{v.total} calls, {v.failed} failed</td></tr>
            ))}
          </tbody></table>
        </div>
      </div>

      <section className="section">
        <h2>AI calls</h2>
        <div className="toolbar" style={{ marginTop: 10 }}>
          <div className="segmented" role="group" aria-label="Filter by status">
            {[["", "All"], ["SUCCESS", "Succeeded"], ["FAILED", "Failed"]].map(([v, l]) => (
              <button key={v} aria-pressed={status === v} onClick={() => setFilter("status", v)}>{l}</button>
            ))}
          </div>
          <select aria-label="Filter by model" value={model} onChange={(e) => setFilter("model", e.target.value)}>
            <option value="">All models</option>
            {Object.keys(m.by_model).map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <select aria-label="Time window" value={hours} onChange={(e) => setFilter("hours", e.target.value)}>
            {Object.entries(WINDOWS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        {runs.error && <ErrorState error={runs.error} onRetry={runs.reload} />}
        {!runs.data && !runs.error && <Loading label="Loading AI calls…" />}
        {runs.data && runs.data.length === 0 && <div className="panel"><Empty title="No AI calls match these filters" /></div>}
        {runs.data && runs.data.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Time</th><th>Claim</th><th>Task</th><th>Model</th><th>Result</th><th className="right">Time taken</th><th>Trace</th></tr></thead>
              <tbody>
                {runs.data.map((r) => (
                  <tr key={r.run_id} className="clickable" onClick={() => navigate(`/runs/${r.run_id}`)}>
                    <td className="num small">{fmtTime(r.created_at)}</td>
                    <td><Link to={`/claims/${r.claim_id}`} onClick={(e) => e.stopPropagation()}>{claimNumber(r.claim_id)}</Link></td>
                    <td className="small">{r.task === "EXTRACTION" ? "Read document" : r.task}</td>
                    <td className="code" style={{ fontSize: 12 }}>{r.model_id}</td>
                    <td>{r.status === "SUCCESS" ? <span className="status-ok">Succeeded</span>
                      : <span className="status-bad">Failed</span>}{r.error_type && <div className="small muted">{errorText(r.error_type)}</div>}</td>
                    <td className="num right">{ms(r.latency_ms)}</td>
                    <td><Link className="code" to={`/runs/${r.run_id}`} onClick={(e) => e.stopPropagation()}>{r.trace_id.slice(0, 10)}…</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function Metric({ label, value, note, bad }) {
  return (
    <div className="metric">
      <div className="label">{label}</div>
      <div className={`value num ${bad ? "bad" : ""}`}>{value}</div>
      {note && <div className="note">{note}</div>}
    </div>
  );
}
