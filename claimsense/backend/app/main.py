from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import Base, engine
from .observability import log_event, tracer
from .routers import claims, graph, observability


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # MVP; switch to Alembic migrations later
    log_event("startup", model=settings.model_label)
    yield


app = FastAPI(title="ClaimSense API", version="0.1.0", lifespan=lifespan,
              description="Synthetic insurance claim verification & fraud flagging. Educational project.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["X-Trace-Id"])


@app.middleware("http")
async def trace_requests(request: Request, call_next):
    with tracer.start_as_current_span(f"HTTP {request.method} {request.url.path}") as span:
        trace_id = format(span.get_span_context().trace_id, "032x")
        t0 = perf_counter()
        response = await call_next(request)
        ms = int((perf_counter() - t0) * 1000)
        response.headers["X-Trace-Id"] = trace_id
        log_event("http_request", trace_id=trace_id, method=request.method, path=request.url.path,
                  status_code=response.status_code, duration_ms=ms)
        return response


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "model": settings.model_label}


app.include_router(claims.router)
app.include_router(observability.router)
app.include_router(graph.router)
