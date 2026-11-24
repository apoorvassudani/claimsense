// Who is signed in, and what their role allows. The server enforces every rule; this only shapes the UI.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, auth } from "./api.js";

const Ctx = createContext(null);
export const ROLE_LABELS = { INTAKE: "Intake", REVIEWER: "Claims reviewer", ADMIN: "Admin" };

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(Boolean(auth.get()));

  useEffect(() => {
    if (!auth.get()) return;
    api.me().then(setUser).catch(() => auth.clear()).finally(() => setChecking(false));
  }, []);

  useEffect(() => {
    const out = () => setUser(null);
    window.addEventListener("claimsense:signed-out", out);
    return () => window.removeEventListener("claimsense:signed-out", out);
  }, []);

  const login = useCallback(async (username, password) => {
    const r = await api.login(username, password);
    auth.set(r.access_token);
    setUser(r.user);
  }, []);

  const logout = useCallback(() => {
    auth.clear();
    setUser(null);
  }, []);

  const can = useCallback((what) => {
    if (!user) return false;
    if (user.role === "ADMIN") return true;
    if (what === "decide" || what === "graph" || what === "monitor") return user.role === "REVIEWER";
    return true;
  }, [user]);

  return <Ctx.Provider value={{ user, checking, login, logout, can }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
