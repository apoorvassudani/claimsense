from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import AIRun, TraceEvent
from ..schemas import RunOut, TraceEventOut

router = APIRouter(prefix="/observability", tags=["observability"])


def p95(values: list[int]) -> int | None:
    if not values:
        return None
    s = sorted(values)
    return s[max(0, int(round(0.95 * len(s) + 0.5)) - 1)]  # nearest-rank


@router.get("/runs", response_model=list[RunOut])
def list_runs(status: str | None = None, model: str | None = None, hours: int | None = None,
              limit: int = 50, db: Session = Depends(get_db)):
    q = select(AIRun).order_by(AIRun.created_at.desc()).limit(min(limit, 500))
    if status:
        q = q.where(AIRun.status == status)
    if model:
        q = q.where(AIRun.model_id == model)
    if hours:
        q = q.where(AIRun.created_at >= datetime.now(timezone.utc) - timedelta(hours=hours))
    return db.scalars(q).all()


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    runs = db.scalars(select(AIRun).where(AIRun.status != "RUNNING").order_by(AIRun.created_at.desc())).all()
    total = len(runs)
    failed = sum(r.status == "FAILED" for r in runs)
    lat = [r.latency_ms for r in runs if r.latency_ms is not None]
    last10 = runs[:10]
    by_model: dict[str, dict] = {}
    for r in runs:
        m = by_model.setdefault(r.model_id, {"total": 0, "failed": 0})
        m["total"] += 1
        m["failed"] += r.status == "FAILED"
    errors: dict[str, int] = {}
    for r in runs:
        if r.error_type:
            errors[r.error_type] = errors.get(r.error_type, 0) + 1
    alerts = []
    if sum(r.status == "FAILED" for r in last10) >= 3:
        alerts.append({"code": "HIGH_FAILURE_RATE", "message": "3 or more of the last 10 AI calls failed"})
    slow = [r.run_id for r in last10 if (r.latency_ms or 0) > settings.slow_call_ms]
    if slow:
        alerts.append({"code": "SLOW_CALL", "message": f"{len(slow)} recent call(s) exceeded "
                                                       f"{settings.slow_call_ms} ms", "run_ids": slow})
    return {"total_runs": total, "success": total - failed, "failed": failed,
            "error_rate": round(failed / total, 3) if total else 0.0,
            "p95_latency_ms": p95(lat), "avg_latency_ms": round(sum(lat) / len(lat)) if lat else None,
            "by_model": by_model, "errors_by_type": errors, "alerts": alerts}


@router.get("/runs/{run_id}")
def run_detail(run_id: str, db: Session = Depends(get_db)):
    run = db.get(AIRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    events = db.scalars(select(TraceEvent).where(TraceEvent.run_id == run_id).order_by(TraceEvent.event_id)).all()
    return {"run": RunOut.model_validate(run), "events": [TraceEventOut.model_validate(e) for e in events]}


@router.get("/traces/{trace_id}")
def trace_detail(trace_id: str, db: Session = Depends(get_db)):
    events = db.scalars(select(TraceEvent).where(TraceEvent.trace_id == trace_id).order_by(TraceEvent.event_id)).all()
    if not events:
        raise HTTPException(404, "trace not found")
    return {"trace_id": trace_id, "events": [TraceEventOut.model_validate(e) for e in events]}
