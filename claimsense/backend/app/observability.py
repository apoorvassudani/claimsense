"""Tracing (OpenTelemetry), structured JSON logs, and stage recording for the trace explorer."""
import json
import logging
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from time import perf_counter

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.trace import Status, StatusCode

from .config import settings

_provider = TracerProvider()
if settings.otel_console:
    _provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(_provider)
tracer = trace.get_tracer("claimsense")

# ---------- structured JSON logging ----------
_logger = logging.getLogger("claimsense")
_logger.setLevel(logging.INFO)
_logger.propagate = False
if not _logger.handlers:
    _logger.addHandler(logging.StreamHandler(sys.stdout))
    try:
        os.makedirs(os.path.dirname(settings.log_file) or ".", exist_ok=True)
        _logger.addHandler(logging.FileHandler(settings.log_file))
    except OSError:
        pass

# Never log these keys, even by accident.
_BLOCKED_KEYS = {"api_key", "text", "text_content", "prompt", "document_text", "phone", "address"}


def log_event(event: str, **fields) -> None:
    record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event}
    record.update({k: v for k, v in fields.items() if k not in _BLOCKED_KEYS and v is not None})
    _logger.info(json.dumps(record, default=str))


def current_trace_id() -> str:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.trace_id else "0" * 32


class StageRecorder:
    """Wraps each pipeline stage in an OTel child span and keeps a row for trace_events."""

    def __init__(self, trace_id: str, run_id: str | None = None):
        self.trace_id = trace_id
        self.run_id = run_id
        self.events: list[dict] = []

    @contextmanager
    def stage(self, name: str):
        started = datetime.now(timezone.utc)
        t0 = perf_counter()
        status, category = "OK", None
        with tracer.start_as_current_span(name) as span:
            if self.run_id:
                span.set_attribute("claimsense.run_id", self.run_id)
            try:
                yield span
            except Exception as exc:
                status = "ERROR"
                category = getattr(exc, "category", type(exc).__name__)
                span.set_status(Status(StatusCode.ERROR, category))
                raise
            finally:
                ms = int((perf_counter() - t0) * 1000)
                self.events.append(dict(trace_id=self.trace_id, run_id=self.run_id, span_name=name,
                                        started_at=started, duration_ms=ms, status=status,
                                        error_category=category))
                log_event("stage", trace_id=self.trace_id, run_id=self.run_id, stage=name,
                          status=status, duration_ms=ms, error_category=category)
