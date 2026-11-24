import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, useApi } from "../api.js";
import { CLAIM_TYPES, DOC_TYPES, REQUIRED_DOCS, fmtDate, inr } from "../format.js";
import { ErrorState, Loading } from "../components/States.jsx";
import { useClaimsIndex } from "../claimsIndex.jsx";

const today = () => new Date().toISOString().slice(0, 10);
const newNumber = () => `CLM-${new Date().getFullYear()}-9${String(Math.floor(Math.random() * 10000)).padStart(4, "0")}`;

export default function NewClaim() {
  const navigate = useNavigate();
  const index = useClaimsIndex();
  const claimants = useApi(() => api.claimants(), []);
  const policies = useApi(() => api.policies(), []);
  const [step, setStep] = useState(1);
  const [claim, setClaim] = useState(null);
  const [form, setForm] = useState({
    claim_number: newNumber(), claimant_code: "", policy_number: "", incident_date: "", reported_date: today(),
    claimed_amount: "", description: "",
  });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [docs, setDocs] = useState([]);
  const [docType, setDocType] = useState("CLAIM_FORM");
  const [file, setFile] = useState(null);
  const [fileKey, setFileKey] = useState(0);

  const myPolicies = useMemo(
    () => (policies.data || []).filter((p) => p.holder_code === form.claimant_code),
    [policies.data, form.claimant_code],
  );
  const policy = (policies.data || []).find((p) => p.policy_number === form.policy_number);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value, ...(k === "claimant_code" ? { policy_number: "" } : {}) }));

  if (claimants.error || policies.error) return <ErrorState error={claimants.error || policies.error} />;
  if (!claimants.data || !policies.data) return <Loading label="Loading claimants and policies…" />;

  async function createClaim(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const c = await api.createClaim({ ...form, claim_type: policy.product_type, claimed_amount: Number(form.claimed_amount) });
      setClaim(c);
      setDocType("CLAIM_FORM");
      setStep(2);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function upload(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const d = await api.upload(claim.claim_id, docType, file);
      setDocs((x) => [...x, d]);
      setFile(null);
      setFileKey((k) => k + 1);
      const next = REQUIRED_DOCS[claim.claim_type].find((t) => t !== docType && ![...docs, d].some((x) => x.doc_type === t));
      if (next) setDocType(next);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setBusy(true);
    setError(null);
    try {
      await api.process(claim.claim_id);
      index.reload(true);
      navigate(`/claims/${claim.claim_id}`);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  const required = claim ? REQUIRED_DOCS[claim.claim_type] : [];
  const missing = required.filter((t) => !docs.some((d) => d.doc_type === t));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>New claim</h1>
          <p className="sub">Enter the claim, attach its documents, then run verification.</p>
        </div>
      </div>
      <nav className="steps" aria-label="Progress">
        <ol>
          {["Claim details", "Documents", "Verify"].map((s, i) => (
            <li key={s} className={step === i + 1 ? "current" : step > i + 1 ? "done" : ""} aria-current={step === i + 1 ? "step" : undefined}>
              {i + 1}. {s}
            </li>
          ))}
        </ol>
      </nav>

      {error && <ErrorState error={error} />}

      {step === 1 && (
        <form className="panel panel-pad" onSubmit={createClaim} style={{ maxWidth: 820 }}>
          <div className="form-grid">
            <label className="field">
              Claimant
              <select required value={form.claimant_code} onChange={set("claimant_code")}>
                <option value="">Choose a claimant</option>
                {claimants.data.map((c) => <option key={c.claimant_code} value={c.claimant_code}>{c.full_name} ({c.claimant_code})</option>)}
              </select>
            </label>
            <label className="field">
              Policy
              <select required value={form.policy_number} onChange={set("policy_number")} disabled={!form.claimant_code}>
                <option value="">{form.claimant_code ? (myPolicies.length ? "Choose a policy" : "No policies for this claimant") : "Choose a claimant first"}</option>
                {myPolicies.map((p) => (
                  <option key={p.policy_number} value={p.policy_number}>{p.policy_number} ({CLAIM_TYPES[p.product_type]})</option>
                ))}
              </select>
              {policy && (
                <span className="hint">
                  {CLAIM_TYPES[policy.product_type]} cover of {inr(policy.sum_insured)}, valid {fmtDate(policy.start_date)} to {fmtDate(policy.end_date)}
                </span>
              )}
            </label>
            <label className="field">
              Claim number
              <input required value={form.claim_number} onChange={set("claim_number")} />
            </label>
            <label className="field">
              Amount claimed (₹)
              <input required type="number" min="1" step="0.01" value={form.claimed_amount} onChange={set("claimed_amount")} />
            </label>
            <label className="field">
              Incident or admission date
              <input required type="date" max={today()} value={form.incident_date} onChange={set("incident_date")} />
            </label>
            <label className="field">
              Reported on
              <input required type="date" max={today()} min={form.incident_date || undefined} value={form.reported_date} onChange={set("reported_date")} />
            </label>
            <label className="field wide">
              What happened
              <textarea value={form.description} onChange={set("description")} maxLength={2000}
                        placeholder="For example: rear-ended at a traffic signal" />
            </label>
          </div>
          <div className="btn-row" style={{ marginTop: 18 }}>
            <button className="btn primary" disabled={busy || !policy}>{busy ? "Creating…" : "Create claim"}</button>
            <Link className="btn" to="/">Cancel</Link>
          </div>
        </form>
      )}

      {step >= 2 && claim && (
        <div className="panel panel-pad" style={{ maxWidth: 820 }}>
          <p style={{ marginBottom: 14 }}>
            <strong>{claim.claim_number}</strong> created for {claim.claimant_name}. A {CLAIM_TYPES[claim.claim_type].toLowerCase()} claim
            needs: {required.map((t) => DOC_TYPES[t]).join(", ")}.
          </p>
          <form className="btn-row" onSubmit={upload} style={{ alignItems: "flex-end" }}>
            <label className="field">
              Document type
              <select value={docType} onChange={(e) => setDocType(e.target.value)}>
                {Object.entries(DOC_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="field">
              File (.txt, .pdf or .md, up to 5 MB)
              <input key={fileKey} type="file" accept=".txt,.pdf,.md" required onChange={(e) => setFile(e.target.files[0] || null)} />
            </label>
            <button className="btn" disabled={!file || busy}>{busy && step === 2 ? "Uploading…" : "Upload"}</button>
          </form>
          <p className="small muted" style={{ marginTop: 8 }}>
            For a demo, use the synthetic files in <span className="code">data/sample_documents</span>.
          </p>

          {docs.length > 0 && (
            <table className="kv" style={{ marginTop: 16 }}><tbody>
              {docs.map((d) => <tr key={d.document_id}><td>{DOC_TYPES[d.doc_type]}</td><td>{d.filename}</td></tr>)}
            </tbody></table>
          )}

          <div style={{ marginTop: 18 }}>
            {missing.length > 0 && docs.length > 0 && (
              <p className="small" style={{ marginBottom: 10 }}>
                Still missing: {missing.map((t) => DOC_TYPES[t]).join(", ")}. You can verify anyway; it will be flagged as a missing document.
              </p>
            )}
            <button className="btn primary" onClick={() => { setStep(3); verify(); }} disabled={!docs.length || busy}>
              {busy && step === 3 ? <><span className="spinner" /> Verifying…</> : "Run verification"}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
