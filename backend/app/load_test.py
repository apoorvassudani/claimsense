"""Load test: many signed-in staff using ClaimSense at the same time.

Usage (from backend/, with the app running):
  python -m app.load_test                                   local API, 20 users, 30 seconds
  python -m app.load_test --url https://YOUR-APP.azurewebsites.net/api --users 20 --duration 60
  python -m app.load_test --include-search                  also hit policy search (makes Azure embedding calls)

Each virtual user signs in once, then repeatedly does what reviewers do: list claims, open a claim, read its
briefing, check monitoring. Verification itself is not load-tested here because every run calls the paid AI
model; AI latency is measured by the observability metrics instead (p95 per model call).

Reports throughput, error rate and p50/p95/p99 latency per request type, and writes docs/load-test-report.md.
Targets: p95 under 1,000 ms and errors under 1%.
"""
import argparse
import asyncio
import random
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .config import settings

REPORT = Path(__file__).resolve().parents[2] / "docs" / "load-test-report.md"
P95_TARGET_MS, ERROR_TARGET = 1000, 0.01


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = max(0, min(len(values) - 1, round(p / 100 * len(values) + 0.5) - 1))
    return values[k]


async def sign_in(client: httpx.AsyncClient, user: str, password: str) -> str:
    r = await client.post("/auth/login", json={"username": user, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


async def virtual_user(client, token, claim_ids, deadline, results, include_search):
    headers = {"Authorization": f"Bearer {token}"}
    actions = [("list claims", 40), ("open claim", 30), ("read briefing", 15), ("monitoring metrics", 10),
               ("health", 5)] + ([("policy search", 10)] if include_search else [])
    names, weights = zip(*actions)
    while time.perf_counter() < deadline:
        action = random.choices(names, weights)[0]
        cid = random.choice(claim_ids)
        path = {"list claims": "/claims", "open claim": f"/claims/{cid}", "read briefing": f"/claims/{cid}/summary",
                "monitoring metrics": "/observability/metrics", "health": "/health",
                "policy search": "/policy/search?q=claim%20reported%20late&product=MOTOR"}[action]
        t0 = time.perf_counter()
        try:
            r = await client.get(path, headers=headers)
            ok = r.status_code < 400
        except httpx.HTTPError:
            ok = False
        results[action].append(((time.perf_counter() - t0) * 1000, ok))
        await asyncio.sleep(random.uniform(0.05, 0.25))  # think time between clicks


async def run(url: str, users: int, duration: int, user: str, password: str, include_search: bool) -> dict:
    limits = httpx.Limits(max_connections=users * 2)
    async with httpx.AsyncClient(base_url=url.rstrip("/"), timeout=30, limits=limits) as client:
        token = await sign_in(client, user, password)
        r = await client.get("/claims", headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        claim_ids = [c["claim_id"] for c in r.json()] or [1]
        print(f"Signed in as {user}; {len(claim_ids)} claims. {users} users for {duration}s against {url} ...")
        tokens = await asyncio.gather(*[sign_in(client, user, password) for _ in range(users)])
        results: dict[str, list] = defaultdict(list)
        start = time.perf_counter()
        deadline = start + duration
        await asyncio.gather(*[virtual_user(client, t, claim_ids, deadline, results, include_search)
                               for t in tokens])
        return {"results": results, "elapsed": time.perf_counter() - start}


def report(url: str, users: int, duration: int, out: dict) -> list[str]:
    res, elapsed = out["results"], out["elapsed"]
    every = [x for v in res.values() for x in v]
    lat = [ms for ms, _ in every]
    errors = sum(1 for _, ok in every if not ok)
    err_rate = errors / len(every) if every else 0
    p95 = pct(lat, 95)
    verdict = "PASS" if p95 < P95_TARGET_MS and err_rate < ERROR_TARGET else "FAIL"
    lines = ["# ClaimSense load test", "",
             f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}. Target: `{url}`. "
             f"{users} concurrent signed-in users for {duration}s (think time 50-250 ms between requests).", "",
             f"**{verdict}**: {len(every)} requests, **{len(every) / elapsed:.1f} req/s**, errors **{errors}** "
             f"({100 * err_rate:.2f}%), p50 **{pct(lat, 50):.0f} ms**, p95 **{p95:.0f} ms**, "
             f"p99 **{pct(lat, 99):.0f} ms** (targets: p95 < {P95_TARGET_MS} ms, errors < {100 * ERROR_TARGET:.0f}%).",
             "", "| Request | Count | Errors | p50 ms | p95 ms | max ms |", "|---|---|---|---|---|---|"]
    for name, v in sorted(res.items(), key=lambda kv: -len(kv[1])):
        ms = [m for m, _ in v]
        lines.append(f"| {name} | {len(v)} | {sum(1 for _, ok in v if not ok)} | {pct(ms, 50):.0f} | "
                     f"{pct(ms, 95):.0f} | {max(ms):.0f} |")
    lines += ["", "Verification (AI calls) is excluded on purpose: each run calls the paid model. AI latency is "
                  "tracked per call in the observability metrics (p95, error rate, slow-call alert).", ""]
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description="ClaimSense load test")
    ap.add_argument("--url", default="http://localhost:8000", help="API base URL (deployed: https://APP/api)")
    ap.add_argument("--users", type=int, default=20)
    ap.add_argument("--duration", type=int, default=30, help="seconds")
    ap.add_argument("--user", default="reviewer01")
    ap.add_argument("--password", default=settings.demo_password or "ClaimSense@2026")
    ap.add_argument("--include-search", action="store_true", help="also call policy search (Azure embeddings)")
    a = ap.parse_args()
    out = asyncio.run(run(a.url, a.users, a.duration, a.user, a.password, a.include_search))
    lines = report(a.url, a.users, a.duration, out)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[4:]))
    print(f"Saved to {REPORT}")


if __name__ == "__main__":
    main()
