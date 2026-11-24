import { useState } from "react";
import { useAuth } from "../auth.jsx";
import { ErrorState } from "../components/States.jsx";

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="panel panel-pad login-card" onSubmit={submit}>
        <div className="login-brand">
          <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
            <rect width="32" height="32" rx="7" fill="#2457A6" />
            <path d="M9 17l5 5 9-12" stroke="#fff" strokeWidth="3.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <h1>ClaimSense</h1>
        </div>
        <p className="small muted" style={{ marginBottom: 18 }}>Sign in with your staff account.</p>
        <label className="field">
          Username
          <input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </label>
        <label className="field" style={{ marginTop: 12 }}>
          Password
          <input type="password" autoComplete="current-password" value={password}
                 onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <div style={{ marginTop: 12 }}><ErrorState error={error} /></div>}
        <button className="btn primary" style={{ marginTop: 16, width: "100%" }} disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="small muted" style={{ marginTop: 16 }}>
          Demo accounts: intake01, reviewer01, admin01. Educational project on synthetic data.
        </p>
      </form>
    </div>
  );
}
