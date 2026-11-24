import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, useApi } from "../api.js";
import {
  CLAIM_TYPES, DECISIONS, DOC_TYPES, EVIDENCE_LABELS, FIELDS, REQUIRED_DOCS, RULES, errorText, fmtDate, fmtTime, inr,
} from "../format.js";
import { RiskBadge, StatusChip } from "../components/Badges.jsx";
import { Empty, ErrorState, Loading } from "../components/States.jsx";
import { useClaimsIndex } from "../claimsIndex.jsx";

export default function ClaimDetail() {
  const { id } = useParams();
  const claim = useApi(() => api.claim(id), [id]);
  const runs = useApi(() => api.runs({ claim_id: id, limit: 30 }), [id]);
  const index = useClaimsIndex();
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState(null);
  const [verifyError, setVerifyError] = useState(null);

  if (claim.error) return <ErrorState error={claim.error} onRetry={claim.reload} />;
  if (!claim.data) return <Loading label="Loading claim…" />;
  const c = claim.data;

  async function verify() {
    setVerifying(true);
    setVerifyError(null);
    setResult(null);
    try {
      const r = await api.process(id);
      setResult(r);
      await Promise.all([claim.reload(true), runs.reload(true)]);
      index.reload(true);
    } catch (e) {
      setVerifyError(e);
    } finally {
      setVerifying(false);
    }
  }

  const missing = (REQUIRED_DOCS[c.claim_type] || []).filter((t) => !c.documents.some((d) => d.doc_type === t));
  const latestTrace = runs.data?.[0]?.trace_id;

  return (
    <>
      <Link className="back" to="/">Claims queue</Link>
      <div className="page-head">
        <div>
          <h1>{c.claim_number}</h1>
          <p className="sub">
            {CLAIM_TYPES[c.claim_type]} claim by {c.claimant_name}, incident on {fmtDate(c.incident_date)}
          </p>
        </div>
        <div className="btn-row">
          <StatusChip status={c.status} />
          <Link className="btn" to={`/graph/${c.claim_id}`}>Open in fraud graph</Link>
          <button className={c.risk_level ? "btn" : "btn primary"} onClick={verify}
                  disabled={verifying || c.documents.length === 0}>
            {verifying ? <><span className="spinner" /> Verifying…</> : c.risk_level ? "Run verification again" : "Run verification"}
          </button>
        </div>
      </div>

      {verifyError && <ErrorState error={verifyError} />}
      {result && <VerifyResult result={result} />}
      {!c.risk_level && c.documents.length > 0 && !result && (
        <div className="notice info">This claim hasn't been verified yet. Run verification to read the documents and check the rules.</div>
      )}
      {c.documents.length === 0 && (
        <div className="notice warn">No documents uploaded. Add documents from the <Link to="/claims/new">new claim</Link> screen.</div>
      )}

      <div className="claim-grid">
        <div>
          <section className="section">
            <h2>{c.findings.length ? "Why this claim was flagged" : "Red flags"}</h2>
            <div className="panel">
              {c.risk_level && c.findings.length === 0 && (
                <Empty title="No red flags found">All 14 rules passed on the information read from the documents.</Empty>
              )}
              {!c.risk_level && <Empty title="Not checked yet">Findings appear after verification.</Empty>}
              {[...c.findings]
                .sort((a, b) => ({ HIGH: 0, MEDIUM: 1, LOW: 2 })[a.severity] - ({ HIGH: 0, MEDIUM: 1, LOW: 2 })[b.severity])
                .map((f, i) => <Finding key={i} f={f} byNumber={index.byNumber} />)}
            </div>
          </section>

          <section className="section">
            <h2>Documents</h2>
            {missing.length > 0 && c.documents.length > 0 && (
              <p className="small muted" style={{ marginBottom: 8 }}>
                Missing for a {CLAIM_TYPES[c.claim_type].toLowerCase()} claim: {missing.map((t) => DOC_TYPES[t]).join(", ")}.
              </p>
            )}
            <Documents claimId={id} documents={c.documents} refreshKey={c.risk_score} />
          </section>

          <section className="section">
            <h2>Claim and policy</h2>
            <div className="panel panel-pad">
              <dl className="facts">
                <Fact label="Claimed amount" value={<span className="num">{inr(c.claimed_amount)}</span>} />
                <Fact label="Sum insured" value={<span className="num">{inr(c.policy.sum_insured)}</span>} />
                <Fact label="Policy number" value={c.policy.policy_number} />
                <Fact label="Policy period" value={`${fmtDate(c.policy.start_date)} to ${fmtDate(c.policy.end_date)}`} />
                <Fact label="Incident date" value={fmtDate(c.incident_date)} />
                <Fact label="Reported on" value={fmtDate(c.reported_date)} />
                <Fact label="Claimant" value={`${c.claimant_name} (${c.claimant_code})`} />
                <Fact label="Description" value={c.description || "—"} />
              </dl>
            </div>
          </section>
        </div>

        <aside className="aside-sticky">
          <RiskPanel claim={c} />
          <div className="panel panel-pad">
            <h2 style={{ marginBottom: 8 }}>AI activity</h2>
            {runs.data?.length ? (
              <>
                <p className="small">
                  {runs.data.filter((r) => r.status === "SUCCESS").length} successful and{" "}
                  {runs.data.filter((r) => r.status === "FAILED").length} failed document readings.
                </p>
                <p className="small muted" style={{ marginTop: 4 }}>
                  Last run {fmtTime(runs.data[0].created_at)} with {runs.data[0].model_id}.
                </p>
                {latestTrace && <p className="small" style={{ marginTop: 8 }}><Link to={`/traces/${latestTrace}`}>See the latest trace</Link></p>}
              </>
            ) : (
              <p className="small muted">No AI runs yet.</p>
            )}
          </div>
          <ReviewPanel claim={c} onSaved={() => { claim.reload(true); index.reload(true); }} />
        </aside>
      </div>
    </>
  );
}

function Fact({ label, value }) {
  return (<div><dt>{label}</dt><dd>{value}</dd></div>);
}

function VerifyResult({ result }) {
  const failed = result.runs.filter((r) => r.status === "FAILED");
  if (failed.length) {
    return (
      <div className="notice warn">
        <strong>The AI couldn't read {failed.length} document{failed.length > 1 ? "s" : ""}</strong> ({errorText(failed[0].error_type).toLowerCase()}).
        The rules ran on everything that was read, and the claim data is unchanged. Run verification again to retry.{" "}
        <Link to={`/traces/${result.trace_id}`}>See what happened</Link>
      </div>
    );
  }
  return (
    <div className="notice ok">
      Verification finished. Risk score {result.risk_score} ({result.risk_level.toLowerCase()}), {result.findings.length} red flag
      {result.findings.length === 1 ? "" : "s"}. <Link to={`/traces/${result.trace_id}`}>See the trace</Link>
    </div>
  );
}

function EvidenceValue({ k, v, byNumber }) {
  if (k === "other_claims") {
    return v.map((n, i) => (
      <span key={n}>{i > 0 && ", "}{byNumber[n] ? <Link to={`/claims/${byNumber[n].claim_id}`}>{n}</Link> : n}</span>
    ));
  }
  if (["claimed", "sum_insured", "bill_total"].includes(k)) return <span className="num">{inr(v)}</span>;
  if (["incident", "start", "end"].includes(k)) return fmtDate(v);
  if (k === "missing") return v.map((t) => DOC_TYPES[t] || t).join(", ");
  if (k === "identifier") return v.replace(/^[A-Z]+:/, "");
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(v))) return fmtDate(v);
  return String(v);
}

function Finding({ f, byNumber }) {
  const sev = { HIGH: "High", MEDIUM: "Medium", LOW: "Low" }[f.severity];
  return (
    <div className="finding">
      <div className={`bar ${f.severity}`} aria-hidden="true" />
      <div>
        <h3>{RULES[f.rule_code] || f.rule_code} <span className="sev">{sev} severity</span></h3>
        <p className="small" style={{ color: "var(--ink-2)", marginTop: 2 }}>{f.message}</p>
        <div className="evidence">
          {Object.entries(f.evidence || {}).map(([k, v]) => (
            <span key={k}><b>{EVIDENCE_LABELS[k] || k}</b><EvidenceValue k={k} v={v} byNumber={byNumber} /></span>
          ))}
        </div>
      </div>
    </div>
  );
}

function Documents({ claimId, documents, refreshKey }) {
  const ex = useApi(() => api.extractions(claimId), [claimId, refreshKey]);
  const [open, setOpen] = useState(null);
  if (!documents.length) return <div className="panel"><Empty title="No documents">Upload documents to verify this claim.</Empty></div>;
  const byDoc = Object.fromEntries((ex.data || []).map((d) => [d.document_id, d.extractions]));
  return (
    <div className="panel">
      {documents.map((d) => {
        const extractions = byDoc[d.document_id] || [];
        const valid = [...extractions].reverse().find((e) => e.is_valid);
        const isOpen = open === d.document_id;
        return (
          <div className="doc-row" key={d.document_id}>
            <button className="doc-toggle" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : d.document_id)}>
              <span>
                <strong>{DOC_TYPES[d.doc_type]}</strong> <span className="small muted">{d.filename}</span>
              </span>
              <span className="small">
                {valid ? <span className="status-ok">Read by AI</span> : ex.data ? <span className="muted">Not read yet</span> : ""}
                <span className="muted" style={{ marginLeft: 10 }}>{isOpen ? "Hide" : "Show"}</span>
              </span>
            </button>
            {isOpen && <DocumentBody doc={d} extraction={valid} />}
          </div>
        );
      })}
    </div>
  );
}

function DocumentBody({ doc, extraction }) {
  const text = useApi(() => api.document(doc.document_id), [doc.document_id]);
  return (
    <div className="doc-body">
      <div>
        <h3 className="small" style={{ marginBottom: 6 }}>Document text</h3>
        {text.error ? <ErrorState error={text.error} /> : <pre className="doc-text">{text.data ? text.data.text : "Loading…"}</pre>}
      </div>
      <div>
        <h3 className="small" style={{ marginBottom: 6 }}>What the AI read</h3>
        {extraction ? (
          <>
            <table className="kv"><tbody>
              {Object.entries(FIELDS).map(([k, label]) => (
                <tr key={k}>
                  <td>{label}</td>
                  <td>{extraction.fields[k] === null || extraction.fields[k] === undefined ? <span className="muted">Not on document</span>
                    : k === "amount" ? <span className="num">{inr(extraction.fields[k])}</span>
                    : k.endsWith("_date") ? fmtDate(extraction.fields[k])
                    : k === "document_type" ? DOC_TYPES[extraction.fields[k]] || extraction.fields[k]
                    : String(extraction.fields[k])}</td>
                </tr>
              ))}
            </tbody></table>
            <p className="small" style={{ marginTop: 8 }}><Link to={`/runs/${extraction.run_id}`}>See how this was read</Link></p>
          </>
        ) : (
          <p className="small muted">Not read yet. Run verification to extract the fields.</p>
        )}
      </div>
    </div>
  );
}

function RiskPanel({ claim }) {
  if (claim.risk_score === null || claim.risk_score === undefined) {
    return <div className="panel panel-pad"><h2>Risk</h2><p className="small muted" style={{ marginTop: 6 }}>Scored after verification.</p></div>;
  }
  return (
    <div className="panel panel-pad">
      <h2 style={{ marginBottom: 10 }}>Risk</h2>
      <div className="score-block">
        <span className={`score-num num ${claim.risk_level}`}>{claim.risk_score}</span>
        <RiskBadge level={claim.risk_level} />
      </div>
      <div className="scale" role="img" aria-label={`Risk score ${claim.risk_score} out of 100`}>
        <span className="marker" style={{ left: `${Math.min(claim.risk_score, 100)}%` }} />
      </div>
      <div className="scale-labels"><span>0</span><span>Review from 20</span><span>100</span></div>
      <p className="small muted" style={{ marginTop: 10 }}>
        High findings add 40, medium 20, low 5. Medium and high claims go to a reviewer.
      </p>
    </div>
  );
}

function ReviewPanel({ claim, onSaved }) {
  const reviews = useApi(() => api.reviews(claim.claim_id), [claim.claim_id]);
  const [decision, setDecision] = useState("");
  const [helpful, setHelpful] = useState("skip");
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(null);
  const verified = claim.risk_level !== null;

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.review(claim.claim_id, {
        decision, comment, ai_helpful: helpful === "skip" ? null : helpful === "yes",
      });
      setSaved(DECISIONS[decision].status);
      setDecision("");
      setComment("");
      setHelpful("skip");
      reviews.reload(true);
      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="panel panel-pad">
      <h2 style={{ marginBottom: 10 }}>Your decision</h2>
      {!verified ? (
        <p className="small muted">Run verification before recording a decision.</p>
      ) : (
        <form onSubmit={submit}>
          <fieldset className="choice" style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="sr-only" style={{ position: "absolute", left: -9999 }}>Decision</legend>
            {Object.entries(DECISIONS).map(([k, d]) => (
              <label key={k}>
                <input type="radio" name="decision" value={k} checked={decision === k} onChange={() => setDecision(k)} />
                <span>{d.label}<span className="help">{d.help}</span></span>
              </label>
            ))}
          </fieldset>
          <p className="small" style={{ margin: "14px 0 6px", fontWeight: 600 }}>Did the AI read the documents correctly?</p>
          <div className="inline-choice">
            {[["yes", "Yes"], ["no", "No"], ["skip", "Not checked"]].map(([v, l]) => (
              <label key={v}><input type="radio" name="helpful" value={v} checked={helpful === v} onChange={() => setHelpful(v)} />{l}</label>
            ))}
          </div>
          <label className="field" style={{ marginTop: 14 }}>
            Notes <span className="hint">What you checked, or what the AI got wrong</span>
            <textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={2000} />
          </label>
          {error && <div style={{ marginTop: 10 }}><ErrorState error={error} /></div>}
          {saved && <div className="notice ok" style={{ marginTop: 10, marginBottom: 0 }}>Decision recorded. Status is now {saved.toLowerCase()}.</div>}
          <button className="btn primary" style={{ marginTop: 12 }} disabled={!decision || saving}>
            {saving ? "Recording…" : "Record decision"}
          </button>
        </form>
      )}
      {reviews.data?.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h3 className="small" style={{ marginBottom: 4 }}>Decision history</h3>
          {reviews.data.map((r) => (
            <div className="review-item" key={r.review_id}>
              <strong>{DECISIONS[r.decision]?.status || r.decision}</strong>{" "}
              <span className="muted">by {r.reviewer_code}, {fmtTime(r.reviewed_at)}</span>
              {r.ai_helpful !== null && <div className="small muted">AI reading {r.ai_helpful ? "correct" : "had mistakes"}</div>}
              {r.comment && <div>{r.comment}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

