import { Link, useParams } from "react-router-dom";
import { useState } from "react";
import { api, useApi } from "../api.js";
import { errorText, fmtTime, ms } from "../format.js";
import Timeline from "../components/Timeline.jsx";
import { ErrorState, Loading } from "../components/States.jsx";
import { useClaimsIndex } from "../claimsIndex.jsx";

/** /runs/:runId shows one AI call; /traces/:traceId shows every stage of one request. */
export default function TraceView() {
  const { runId, traceId } = useParams();
  const run = useApi(() => (runId ? api.run(runId) : Promise.resolve(null)), [runId]);
  const tid = traceId || run.data?.run.trace_id;
  const trace = useApi(() => (tid ? api.trace(tid) : Promise.resolve(null)), [tid]);
  const index = useClaimsIndex();
  const [copied, setCopied] = useState(false);

  if (run.error) return <ErrorState error={run.error} onRetry={run.reload} />;
  if (trace.error) return <ErrorState error={trace.error} onRetry={trace.reload} />;
  if ((runId && !run.data) || !trace.data) return <Loading label="Loading trace…" />;
  const r = run.data?.run;
  const claimId = r?.claim_id;
  const claim = claimId && index.claims.find((c) => c.claim_id === claimId);

  const copy = () => navigator.clipboard?.writeText(tid).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); });

  return (
    <>
      <Link className="back" to="/monitoring">Monitoring</Link>
      <div className="page-head">
        <div>
          <h1>{r ? "AI call" : "Request trace"}</h1>
          <p className="sub">
            Trace <span className="code">{tid}</span>{" "}
            <button className="btn" style={{ padding: "2px 8px", fontSize: 12.5 }} onClick={copy}>{copied ? "Copied" : "Copy"}</button>
          </p>
        </div>
      </div>

      {r && (
        <div className="panel panel-pad section">
          <dl className="facts">
            <div><dt>Result</dt><dd>{r.status === "SUCCESS" ? <span className="status-ok">Succeeded</span> : <span className="status-bad">Failed</span>}</dd></div>
            {r.error_type && <div><dt>Why it failed</dt><dd>{errorText(r.error_type)}</dd></div>}
            <div><dt>Time taken</dt><dd className="num">{ms(r.latency_ms)}</dd></div>
            <div><dt>Model</dt><dd className="code">{r.model_id}</dd></div>
            <div><dt>Prompt version</dt><dd>{r.prompt_version}</dd></div>
            <div><dt>Claim</dt><dd><Link to={`/claims/${r.claim_id}`}>{claim?.claim_number || `#${r.claim_id}`}</Link></dd></div>
            <div><dt>Started</dt><dd>{fmtTime(r.created_at)}</dd></div>
            {(r.input_tokens || r.output_tokens) && <div><dt>Tokens</dt><dd className="num">{r.input_tokens ?? "—"} in, {r.output_tokens ?? "—"} out</dd></div>}
          </dl>
        </div>
      )}

      {r && (
        <section className="section">
          <h2>Stages of this AI call</h2>
          <div className="panel panel-pad" style={{ marginTop: 10 }}><Timeline events={run.data.events} /></div>
        </section>
      )}

      <section className="section">
        <h2>{r ? "The whole request" : "Stages"}</h2>
        <p className="small muted" style={{ margin: "4px 0 10px" }}>
          Every step that shared this trace ID, from reading documents to scoring the claim. Failures show in red; claim data is
          never changed by a failed AI call.
        </p>
        <div className="panel panel-pad"><Timeline events={trace.data.events} /></div>
      </section>
    </>
  );
}
