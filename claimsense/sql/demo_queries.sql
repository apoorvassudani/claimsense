-- 1. Risk overview: claims by risk level with total claimed amount
SELECT risk_level, COUNT(*) AS claims, SUM(claimed_amount) AS total_claimed
FROM claims GROUP BY risk_level ORDER BY claims DESC;

-- 2. Most frequent fraud rules (JOIN + aggregation)
SELECT f.rule_code, f.severity, COUNT(DISTINCT f.claim_id) AS claims_flagged
FROM validation_findings f GROUP BY f.rule_code, f.severity ORDER BY claims_flagged DESC;

-- 3. AI reliability: runs, failures, avg & p95 latency by model and status
SELECT model_id, status, COUNT(*) AS runs, ROUND(AVG(latency_ms)) AS avg_ms,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms
FROM ai_runs GROUP BY model_id, status;

-- 4. Failed or slow AI runs together with their trace stages
SELECT r.run_id, r.status, r.error_type, r.latency_ms, t.span_name, t.duration_ms, t.status AS span_status
FROM ai_runs r JOIN trace_events t ON t.run_id = r.run_id
WHERE r.status = 'FAILED' OR r.latency_ms > 5000 ORDER BY r.created_at DESC, t.event_id;

-- 5. Graph: identifiers shared by more than one claim (possible rings)
SELECT n.node_type, n.label, COUNT(DISTINCT e.src_node_id) AS linked_claims
FROM graph_nodes n JOIN graph_edges e ON e.dst_node_id = n.node_id
WHERE n.node_type IN ('PHONE','ADDRESS','PROVIDER','VEHICLE')
GROUP BY n.node_type, n.label HAVING COUNT(DISTINCT e.src_node_id) > 1 ORDER BY linked_claims DESC;
