// Shared list of claims so any screen can turn a claim number into a link.
import { createContext, useContext } from "react";
import { api, useApi } from "./api.js";

const Ctx = createContext({ claims: [], byNumber: {}, reload: () => {} });

export function ClaimsIndexProvider({ children }) {
  const { data, reload } = useApi(() => api.claims(), []);
  const claims = data || [];
  const byNumber = Object.fromEntries(claims.map((c) => [c.claim_number, c]));
  return <Ctx.Provider value={{ claims, byNumber, reload }}>{children}</Ctx.Provider>;
}

export const useClaimsIndex = () => useContext(Ctx);
