// All calls go to the ClaimSense FastAPI backend. The browser never talks to the AI provider
// and never holds API keys.
import { useCallback, useEffect, useRef, useState } from "react";

export const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, status, traceId) {
    super(message);
    this.status = status;
    this.traceId = traceId;
  }
}

// Sign-in token for this browser tab (cleared when the tab closes). Every request sends it.
const TOKEN_KEY = "claimsense.token";
export const auth = {
  get: () => { try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set: (t) => { try { sessionStorage.setItem(TOKEN_KEY, t); } catch { /* storage unavailable */ } },
  clear: () => { try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ } },
};

function qs(params = {}) {
  const p = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return p.length ? "?" + new URLSearchParams(p).toString() : "";
}

async function request(path, { method = "GET", body, form } = {}) {
  let res;
  try {
    const headers = {};
    if (body) headers["Content-Type"] = "application/json";
    const token = auth.get();
    if (token) headers.Authorization = `Bearer ${token}`;
    res = await fetch(API_URL + path, {
      method,
      headers,
      body: form ?? (body ? JSON.stringify(body) : undefined),
    });
  } catch {
    throw new ApiError(
      `Can't reach the ClaimSense API at ${API_URL}. Start the backend with "uvicorn app.main:app --reload", then try again.`,
      0,
    );
  }
  const traceId = res.headers.get("X-Trace-Id");
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (res.status === 401 && path !== "/auth/login") {
    auth.clear();
    window.dispatchEvent(new Event("claimsense:signed-out"));  // back to the sign-in screen
  }
  if (!res.ok) {
    const detail = data && data.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => `${(d.loc || []).slice(-1)[0] || "field"}: ${d.msg}`).join("; ")
      : detail || `The request failed with status ${res.status}.`;
    throw new ApiError(message, res.status, traceId);
  }
  return data;
}

export const api = {
  login: (username, password) => request("/auth/login", { method: "POST", body: { username, password } }),
  me: () => request("/auth/me"),
  health: () => request("/health"),
  claims: (params) => request(`/claims${qs(params)}`),
  claim: (id) => request(`/claims/${id}`),
  extractions: (id) => request(`/claims/${id}/extractions`),
  summary: (id) => request(`/claims/${id}/summary`),
  document: (id) => request(`/documents/${id}`),
  createClaim: (body) => request("/claims", { method: "POST", body }),
  upload: (id, docType, file) => {
    const form = new FormData();
    form.append("doc_type", docType);
    form.append("file", file);
    return request(`/claims/${id}/documents`, { method: "POST", form });
  },
  process: (id) => request(`/claims/${id}/process`, { method: "POST" }),
  reviews: (id) => request(`/claims/${id}/reviews`),
  review: (id, body) => request(`/claims/${id}/reviews`, { method: "POST", body }),
  policies: () => request("/policies"),
  claimants: () => request("/claimants"),
  graph: (id) => request(`/graph/claims/${id}`),
  runs: (params) => request(`/observability/runs${qs(params)}`),
  run: (id) => request(`/observability/runs/${id}`),
  trace: (id) => request(`/observability/traces/${id}`),
  metrics: () => request("/observability/metrics"),
};

/** Load data from the API with loading/error state. `deps` re-run the request when they change. */
export function useApi(fn, deps = [], { refreshMs } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const load = useCallback(
    (quiet = false) => {
      if (!quiet) setState((s) => ({ ...s, loading: true, error: null }));
      return fnRef
        .current()
        .then((data) => setState({ data, error: null, loading: false }))
        .catch((error) => setState((s) => ({ data: quiet ? s.data : null, error, loading: false })));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    deps,
  );
  useEffect(() => {
    load();
    if (!refreshMs) return undefined;
    const t = setInterval(() => load(true), refreshMs);
    return () => clearInterval(t);
  }, [load, refreshMs]);
  return { ...state, reload: load };
}
