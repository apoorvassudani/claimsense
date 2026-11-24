"""OCR: turn a scanned image (or scanned PDF) into text, then the normal extraction step reads that text.

Two interchangeable engines behind one function:
  docintel : Azure AI Document Intelligence, prebuilt-read model (purpose-built OCR)
  vision   : the Azure OpenAI chat deployment reading the image directly (gpt-4.1-mini is multimodal)
OCR_PROVIDER=auto picks Document Intelligence when its endpoint and key are set, otherwise vision.
Each OCR call is recorded as an AI run (task OCR) with timing, so it shows in traces and monitoring.
"""
import time
from dataclasses import dataclass
from time import perf_counter

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AIRun, TraceEvent
from ..observability import StageRecorder, current_trace_id, log_event, tracer
from . import llm

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


class OCRError(llm.LLMError):
    category = "ocr_error"


@dataclass
class OCRResult:
    text: str
    engine: str          # "docintel" or "vision"
    model_id: str        # what is recorded on the AI run
    input_tokens: int | None = None
    output_tokens: int | None = None


def engine() -> str | None:
    """Which OCR engine is active, or None if scans can't be read in this configuration."""
    choice = settings.ocr_provider.lower()
    docintel_ready = bool(settings.azure_docintel_endpoint and settings.azure_docintel_api_key)
    vision_ready = settings.llm_provider == "azure" and bool(settings.azure_openai_chat_deployment)
    if choice == "docintel":
        return "docintel" if docintel_ready else None
    if choice == "vision":
        return "vision" if vision_ready else None
    if choice == "auto":
        return "docintel" if docintel_ready else ("vision" if vision_ready else None)
    return None


def engine_label() -> str:
    e = engine()
    if e == "docintel":
        return "azure-docintel:prebuilt-read"
    if e == "vision":
        return f"vision:{settings.azure_openai_chat_deployment}"
    return "none"


# ---------------------------------------------------------------- engines
def _docintel(data: bytes, mime: str) -> OCRResult:
    base = settings.azure_docintel_endpoint.rstrip("/")
    url = (f"{base}/documentintelligence/documentModels/prebuilt-read:analyze"
           f"?api-version={settings.azure_docintel_api_version}")
    headers = {"Ocp-Apim-Subscription-Key": settings.azure_docintel_api_key, "Content-Type": mime}
    try:
        resp = httpx.post(url, headers=headers, content=data, timeout=settings.llm_timeout_s)
        if resp.status_code == 429:
            raise llm.LLMQuota("document intelligence rate limit")
        if resp.status_code >= 400:
            err = OCRError(f"http_{resp.status_code}: {resp.text[:200]}")
            err.category = f"http_{resp.status_code}"
            raise err
        poll = resp.headers.get("operation-location")
        if not poll:
            raise OCRError("no operation-location header")
        deadline = time.monotonic() + settings.llm_timeout_s * 3
        while True:  # analysis is asynchronous: poll until it finishes
            time.sleep(1)
            r = httpx.get(poll, headers={"Ocp-Apim-Subscription-Key": settings.azure_docintel_api_key},
                          timeout=settings.llm_timeout_s)
            body = r.json()
            status = body.get("status")
            if status == "succeeded":
                return OCRResult(text=body["analyzeResult"]["content"], engine="docintel",
                                 model_id="azure-docintel:prebuilt-read")
            if status == "failed":
                raise OCRError(f"analysis failed: {body.get('error', {}).get('message', '')[:200]}")
            if time.monotonic() > deadline:
                raise llm.LLMTimeout("document intelligence analysis did not finish in time")
    except httpx.TimeoutException as exc:
        raise llm.LLMTimeout(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise OCRError(type(exc).__name__) from exc
    except (ValueError, KeyError) as exc:
        raise llm.LLMMalformed("unexpected document intelligence payload") from exc


def _vision(data: bytes, mime: str) -> OCRResult:
    if mime == "application/pdf":
        raise OCRError("scanned PDFs need Document Intelligence; with vision OCR, upload the pages as PNG/JPG")
    r = llm.vision_transcribe(data, mime)
    return OCRResult(text=r.text, engine="vision", model_id=r.model,
                     input_tokens=r.input_tokens, output_tokens=r.output_tokens)


def read(data: bytes, mime: str) -> OCRResult:
    """OCR without any database bookkeeping (used by the scan evaluation)."""
    e = engine()
    if e is None:
        raise OCRError("OCR is not configured: set AZURE_DOCINTEL_* or use LLM_PROVIDER=azure for vision OCR")
    result = _docintel(data, mime) if e == "docintel" else _vision(data, mime)
    if not result.text.strip():
        raise OCRError("OCR found no text")
    return result


def read_for_upload(db: Session, claim_id: int, data: bytes, mime: str) -> tuple[OCRResult | None, AIRun]:
    """OCR an uploaded file and record it as an AI run. Returns (result or None if it failed, run)."""
    with tracer.start_as_current_span("document.ocr"):
        trace_id = current_trace_id()
        run = AIRun(claim_id=claim_id, task="OCR", trace_id=trace_id, model_id=engine_label(),
                    prompt_version="ocr-v1", status="RUNNING")
        db.add(run)
        db.flush()
        rec = StageRecorder(trace_id, run.run_id)
        t0 = perf_counter()
        result = None
        try:
            with rec.stage("ocr.read"):
                result = read(data, mime)
            run.status, run.model_id = "SUCCESS", result.model_id if result.engine == "docintel" else engine_label()
            run.input_tokens, run.output_tokens = result.input_tokens, result.output_tokens
        except Exception as exc:
            run.status, run.error_type = "FAILED", getattr(exc, "category", "internal_error")
        run.latency_ms = int((perf_counter() - t0) * 1000)
        for ev in rec.events:
            db.add(TraceEvent(**ev))
        log_event("ai_run", trace_id=trace_id, run_id=run.run_id, claim_id=claim_id, task="OCR",
                  model=run.model_id, status=run.status, latency_ms=run.latency_ms, error_category=run.error_type)
        return result, run
