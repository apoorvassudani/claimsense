import { Suspense, lazy } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { ClaimsIndexProvider } from "./claimsIndex.jsx";
import ClaimsQueue from "./pages/ClaimsQueue.jsx";
import ClaimDetail from "./pages/ClaimDetail.jsx";
import NewClaim from "./pages/NewClaim.jsx";
import TraceView from "./pages/TraceView.jsx";
import { Empty, Loading } from "./components/States.jsx";

const GraphExplorer = lazy(() => import("./pages/GraphExplorer.jsx"));
const Monitoring = lazy(() => import("./pages/Monitoring.jsx"));

const icons = {
  queue: <path d="M4 6h16M4 12h16M4 18h10" />,
  add: <path d="M12 5v14M5 12h14" />,
  graph: (
    <>
      <circle cx="6" cy="7" r="2.5" /><circle cx="18" cy="6" r="2.5" /><circle cx="12" cy="17" r="2.5" />
      <path d="M8.2 8.3l2.6 6.4M15.9 7.6l-2.8 7.2M8.5 6.8l7-.6" />
    </>
  ),
  pulse: <path d="M3 12h4l2.5-6 4 12 2.5-6H21" />,
};
const Icon = ({ name }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{icons[name]}</svg>
);

export default function App() {
  return (
    <ClaimsIndexProvider>
      <div className="shell">
        <aside className="sidebar">
          <div className="brand">
            <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
              <rect width="32" height="32" rx="7" fill="#2457A6" />
              <path d="M9 17l5 5 9-12" stroke="#fff" strokeWidth="3.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            ClaimSense
          </div>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end><Icon name="queue" />Claims queue</NavLink>
            <NavLink to="/claims/new"><Icon name="add" />New claim</NavLink>
            <NavLink to="/graph"><Icon name="graph" />Fraud graph</NavLink>
            <NavLink to="/monitoring"><Icon name="pulse" />Monitoring</NavLink>
          </nav>
          <p className="sidebar-note">
            Educational project on synthetic data. ClaimSense flags claims for review. People make the decisions.
          </p>
        </aside>
        <main className="main">
          <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<ClaimsQueue />} />
            <Route path="/claims/new" element={<NewClaim />} />
            <Route path="/claims/:id" element={<ClaimDetail />} />
            <Route path="/graph" element={<GraphExplorer />} />
            <Route path="/graph/:id" element={<GraphExplorer />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="/runs/:runId" element={<TraceView />} />
            <Route path="/traces/:traceId" element={<TraceView />} />
            <Route path="*" element={<Empty title="This page doesn't exist">Use the menu to go back to the claims queue.</Empty>} />
          </Routes>
          </Suspense>
        </main>
      </div>
    </ClaimsIndexProvider>
  );
}
