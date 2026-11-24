import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3-force";
import { api, useApi } from "../api.js";
import { CLAIM_TYPES, RULES } from "../format.js";
import { RiskBadge } from "../components/Badges.jsx";
import { Empty, ErrorState, Loading } from "../components/States.jsx";
import { useClaimsIndex } from "../claimsIndex.jsx";

const RING_RULES = ["PROVIDER_CLUSTER", "SHARED_PHONE", "SHARED_VEHICLE", "DUPLICATE_INVOICE", "DUPLICATE_DOCUMENT"];
const RISK_COLOR = { HIGH: "#B42318", MEDIUM: "#B7791F", LOW: "#2F7D5B" };
const TYPE_NAME = {
  CLAIMANT: "Person", POLICY: "Policy", PHONE: "Phone", ADDRESS: "Address", PROVIDER: "Garage, hospital or contractor",
  VEHICLE: "Vehicle",
};
const HEIGHT = 560;

export default function GraphExplorer() {
  const { id } = useParams();
  const navigate = useNavigate();
  const index = useClaimsIndex();
  const [query, setQuery] = useState("");

  const suggestions = useMemo(
    () => index.claims.filter((c) => c.rule_codes.some((r) => RING_RULES.includes(r))).slice(0, 8),
    [index.claims],
  );

  function openNumber(e) {
    e.preventDefault();
    const c = index.byNumber[query.trim().toUpperCase()];
    if (c) navigate(`/graph/${c.claim_id}`);
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Fraud graph</h1>
          <p className="sub">
            How a claim connects to people, phones, addresses, garages, hospitals and vehicles, and to other claims that share them.
          </p>
        </div>
      </div>
      <form className="toolbar" onSubmit={openNumber}>
        <input list="claim-numbers" className="grow" placeholder="Enter a claim number, for example CLM-2026-00067"
               aria-label="Claim number" value={query} onChange={(e) => setQuery(e.target.value)} />
        <datalist id="claim-numbers">
          {index.claims.map((c) => <option key={c.claim_id} value={c.claim_number} />)}
        </datalist>
        <button className="btn primary" disabled={!index.byNumber[query.trim().toUpperCase()]}>Show graph</button>
      </form>
      {suggestions.length > 0 && (
        <div style={{ marginBottom: 18 }}>
          <p className="small muted" style={{ marginBottom: 6 }}>Claims with links to other claims:</p>
          <div className="chips">
            {suggestions.map((c) => (
              <button key={c.claim_id} onClick={() => navigate(`/graph/${c.claim_id}`)}>{c.claim_number}</button>
            ))}
          </div>
        </div>
      )}
      {id ? <ClaimGraph id={id} /> : (
        <div className="panel"><Empty title="Choose a claim to explore">Pick one of the suggested claims or enter a claim number.</Empty></div>
      )}
    </>
  );
}

function ClaimGraph({ id }) {
  const navigate = useNavigate();
  const index = useClaimsIndex();
  const graph = useApi(() => api.graph(id), [id]);
  const claim = useApi(() => api.claim(id), [id]);
  const wrap = useRef(null);
  const [width, setWidth] = useState(800);

  useEffect(() => {
    if (!wrap.current) return undefined;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(320, Math.floor(e.contentRect.width))));
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, [graph.data]);

  const layout = useMemo(() => {
    if (!graph.data?.nodes.length || !claim.data) return null;
    const degree = {};
    graph.data.edges.forEach((e) => { degree[e.target] = (degree[e.target] || 0) + 1; });
    const nodes = graph.data.nodes.map((n) => {
      const isSelf = n.type === "CLAIM" && n.label === claim.data.claim_number;
      return { ...n, isSelf, shared: n.type !== "CLAIM" && (degree[n.id] || 0) > 1, other: n.type === "CLAIM" && !isSelf };
    });
    const self = nodes.find((n) => n.isSelf);
    if (self) { self.fx = width / 2; self.fy = HEIGHT / 2; }
    const links = graph.data.edges.map((e) => ({ ...e }));
    const spread = nodes.length < 14 ? 1.5 : nodes.length < 30 ? 1.15 : 1;  // small graphs use more of the canvas
    forceSimulation(nodes)
      .force("link", forceLink(links).id((d) => d.id)
        .distance((l) => (l.target.shared || l.source.other ? 125 : 90) * spread).strength(0.9))
      .force("charge", forceManyBody().strength((d) => (d.type === "CLAIM" ? -900 : -500) * spread))
      .force("collide", forceCollide((d) => (d.type === "CLAIM" ? 62 : 44)).strength(1).iterations(3))
      .force("x", forceX(width / 2).strength(0.04))
      .force("y", forceY(HEIGHT / 2).strength(0.06))
      .force("center", forceCenter(width / 2, HEIGHT / 2))
      .stop()
      .tick(320);
    nodes.forEach((n) => {
      n.x = Math.max(60, Math.min(width - 60, n.x));
      n.y = Math.max(34, Math.min(HEIGHT - 40, n.y));
    });
    return { nodes, links };
  }, [graph.data, claim.data, width]);

  if (graph.error || claim.error) return <ErrorState error={graph.error || claim.error} onRetry={() => { graph.reload(); claim.reload(); }} />;
  if (!graph.data || !claim.data) return <Loading label="Building the graph…" />;
  const c = claim.data;
  const shared = Object.entries(graph.data.shared_identifiers || {});

  return (
    <div className="graph-layout">
      <div className="graph-canvas" ref={wrap}>
        {!layout ? (
          <Empty title="No graph for this claim yet">Run verification on the claim first. The graph is built from what the AI reads.</Empty>
        ) : (
          <svg viewBox={`0 0 ${width} ${HEIGHT}`} height={HEIGHT} role="img"
               aria-label={`Relationship graph for ${c.claim_number}. ${shared.length} items shared with other claims.`}>
            {layout.links.map((l, i) => {
              const hot = l.target.shared;
              return (
                <line key={i} x1={l.source.x} y1={l.source.y} x2={l.target.x} y2={l.target.y}
                      stroke={hot ? "#2457A6" : "#C5CDD8"} strokeWidth={hot ? 2 : 1.2} strokeOpacity={hot ? 0.75 : 1} />
              );
            })}
            {layout.nodes.map((n) => <Node key={n.id} n={n} index={index} navigate={navigate} />)}
          </svg>
        )}
      </div>

      <aside className="aside-sticky">
        <div className="panel panel-pad">
          <h2>{c.claim_number}</h2>
          <p className="small muted" style={{ margin: "4px 0 10px" }}>{CLAIM_TYPES[c.claim_type]} claim by {c.claimant_name}</p>
          <RiskBadge level={c.risk_level} score={c.risk_score} />
          {c.findings.length > 0 && (
            <p className="small" style={{ marginTop: 8 }}>{c.findings.map((f) => RULES[f.rule_code] || f.rule_code).join("; ")}</p>
          )}
          <Link className="btn" style={{ marginTop: 12 }} to={`/claims/${c.claim_id}`}>Open claim file</Link>
        </div>

        <div className="panel panel-pad">
          <h2 style={{ marginBottom: 4 }}>Shared with other claims</h2>
          {shared.length === 0 ? (
            <p className="small muted">Nothing. This claim's phone, address, provider and vehicle aren't on any other claim.</p>
          ) : shared.map(([ident, numbers]) => {
            const [type, ...rest] = ident.split(":");
            return (
              <div className="shared-item" key={ident}>
                <strong>{TYPE_NAME[type] || type}</strong>: {rest.join(":")}
                <div>
                  {numbers.map((n, i) => (
                    <span key={n}>{i > 0 && ", "}{index.byNumber[n] ? <Link to={`/graph/${index.byNumber[n].claim_id}`}>{n}</Link> : n}</span>
                  ))}
                </div>
              </div>
            );
          })}
          <p className="small muted" style={{ marginTop: 10 }}>
            A shared address alone isn't a red flag (families share homes). Shared phones, vehicles and bursts of claims at one
            provider are.
          </p>
        </div>

        <div className="panel panel-pad">
          <h2 style={{ marginBottom: 10 }}>Key</h2>
          <div className="legend">
            <div><svg width="22" height="22"><circle cx="11" cy="11" r="9" fill="#1B2433" /></svg>This claim</div>
            <div><svg width="22" height="22"><circle cx="11" cy="11" r="8" fill="#B42318" /></svg>Other claim, coloured by risk</div>
            <div><svg width="22" height="22"><rect x="4" y="4" width="14" height="14" rx="3" fill="#fff" stroke="#2457A6" strokeWidth="2.5" /></svg>Shared with another claim</div>
            <div><svg width="22" height="22"><rect x="4" y="4" width="14" height="14" rx="3" fill="#fff" stroke="#9AA5B6" strokeWidth="1.5" /></svg>Phone, address, provider or vehicle</div>
            <div><svg width="22" height="22"><circle cx="11" cy="11" r="7" fill="#fff" stroke="#6B7686" strokeWidth="1.5" /></svg>Person or policy</div>
          </div>
          <p className="small muted" style={{ marginTop: 10 }}>Select another claim in the graph to explore from it.</p>
        </div>
      </aside>
    </div>
  );
}

function truncate(s, n = 24) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function Node({ n, index, navigate }) {
  const target = n.other ? index.byNumber[n.label] : null;
  const go = () => target && navigate(`/graph/${target.claim_id}`);
  const label = n.type === "CLAIM" ? n.label : truncate(n.label);
  let shape;
  if (n.type === "CLAIM") {
    const fill = n.isSelf ? "#1B2433" : RISK_COLOR[target?.risk_level] || "#9AA5B6";
    shape = <circle r={n.isSelf ? 20 : 14} fill={fill} stroke="#fff" strokeWidth="2.5" />;
  } else if (n.type === "CLAIMANT" || n.type === "POLICY") {
    shape = <circle r={9} fill="#fff" stroke="#6B7686" strokeWidth="1.5" />;
  } else {
    shape = (
      <rect x={-11} y={-11} width={22} height={22} rx={4} fill="#fff"
            stroke={n.shared ? "#2457A6" : "#9AA5B6"} strokeWidth={n.shared ? 2.5 : 1.5} />
    );
  }
  const r = n.isSelf ? 20 : n.type === "CLAIM" ? 14 : 11;
  return (
    <g className={`node ${target ? "claim-link" : ""}`} transform={`translate(${n.x},${n.y})`}
       tabIndex={target ? 0 : undefined} role={target ? "link" : undefined}
       aria-label={target ? `Explore ${n.label}` : undefined}
       onClick={go} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), go())}>
      <title>{`${n.type === "CLAIM" ? "Claim" : TYPE_NAME[n.type]}: ${n.label}`}</title>
      {shape}
      <text y={r + 15} textAnchor="middle" fontSize={n.type === "CLAIM" ? 12.5 : 11.5}
            fontWeight={n.type === "CLAIM" || n.shared ? 600 : 400}
            fill={n.shared ? "#2457A6" : "#1B2433"} paintOrder="stroke" stroke="#fff" strokeWidth="4" strokeLinejoin="round">
        {label}
      </text>
    </g>
  );
}
