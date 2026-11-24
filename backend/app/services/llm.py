"""Hosted-model client (Azure OpenAI, or any OpenAI-compatible API such as Groq) plus an offline mock.
All provider errors are mapped to a small set of categories used in traces and metrics."""
import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..config import settings


class LLMError(Exception):
    category = "provider_error"


class LLMTimeout(LLMError):
    category = "timeout"


class LLMQuota(LLMError):
    category = "quota"


class LLMMalformed(LLMError):
    category = "malformed_response"


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


_LABELS = {
    "document type": "document_type", "policy number": "policy_number", "claimant name": "claimant_name",
    "patient name": "claimant_name", "incident date": "incident_date", "date of incident": "incident_date",
    "document date": "document_date", "invoice number": "invoice_number", "bill number": "invoice_number",
    "provider": "provider_name", "hospital": "provider_name", "garage": "provider_name",
    "vehicle registration": "vehicle_registration", "phone": "phone", "total amount": "amount",
    "claimed amount": "amount", "amount": "amount",
}


GROUND_TRUTH = Path(__file__).resolve().parents[3] / "data" / "ground_truth.json"
_truth_cache: dict[str, dict] | None = None


def _truth_fields(document_text: str) -> dict | None:
    """Offline mode: return the answer-key fields for a known synthetic document (matched by text hash)."""
    global _truth_cache
    if _truth_cache is None:
        _truth_cache = {}
        if GROUND_TRUTH.exists():
            data = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
            for c in data.get("claims", []):
                for d in c.get("documents", []):
                    _truth_cache[d["sha256"]] = d["fields"]
    return _truth_cache.get(hashlib.sha256(document_text.encode("utf-8")).hexdigest())


def reset_truth_cache() -> None:
    global _truth_cache
    _truth_cache = None


def _mock_extract(document_text: str) -> str:
    """Offline extractor: answer-key fields for seeded documents, else a simple 'Label: value' parser."""
    known = _truth_fields(document_text)
    if known is not None:
        return json.dumps(known | {"confidence_notes": ["mock: answer-key fields"]})
    out: dict = {k: None for k in set(_LABELS.values())}
    out["confidence_notes"] = ["mock extractor: label-based parsing"]
    for line in document_text.splitlines():
        m = re.match(r"\s*([A-Za-z ]+?)\s*:\s*(.+)$", line)
        if not m:
            continue
        key = _LABELS.get(m.group(1).strip().lower())
        if key and out.get(key) is None:
            val = m.group(2).strip()
            if key == "amount":
                val = re.sub(r"[^0-9.]", "", val) or None
            out[key] = val
    if out["document_type"]:
        out["document_type"] = out["document_type"].upper().replace(" ", "_")
    else:
        out["document_type"] = "OTHER"
    return json.dumps(out)


MAX_RETRIES = 3


def _retry_wait(resp: httpx.Response, attempt: int) -> float:
    """Seconds to wait before retrying a 429: use Retry-After if given, else back off 2s, 4s, 8s."""
    try:
        wait = float(resp.headers.get("retry-after", ""))
    except ValueError:
        wait = 2.0 * (2 ** attempt)
    return min(max(wait, 1.0), 20.0)


def _azure_url(deployment: str, operation: str) -> str:
    """Azure puts the deployment name in the URL and needs an api-version query parameter."""
    if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
        raise LLMError("AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY not configured")
    if not deployment:
        raise LLMError(f"Azure deployment name for {operation} not configured")
    return (f"{settings.azure_openai_endpoint.rstrip('/')}/openai/deployments/{deployment}/{operation}"
            f"?api-version={settings.azure_openai_api_version}")


def _chat_request(system_prompt: str, user_prompt: str) -> tuple[str, dict, dict]:
    """Build URL, headers and body for the configured provider."""
    body: dict = {
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": user_prompt}],
    }
    if settings.llm_temperature.strip():
        body["temperature"] = float(settings.llm_temperature)

    if settings.llm_provider == "azure":
        url = _azure_url(settings.azure_openai_chat_deployment, "chat/completions")
        return url, {"api-key": settings.azure_openai_api_key}, body

    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY not configured")
    body["model"] = settings.llm_model
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    return url, {"Authorization": f"Bearer {settings.llm_api_key}"}, body


def complete_json(system_prompt: str, user_prompt: str, document_text: str) -> LLMResult:
    sim = settings.simulate_failure
    if sim == "timeout":
        raise LLMTimeout("simulated provider timeout")
    if sim == "quota":
        raise LLMQuota("simulated quota exceeded")
    if sim == "slow":
        time.sleep(settings.slow_call_ms / 1000 + 0.5)

    if settings.llm_provider == "mock":
        text = "{not valid json" if sim == "malformed" else _mock_extract(document_text)
        return LLMResult(text=text, model=settings.model_label)

    url, headers, body = _chat_request(system_prompt, user_prompt)
    return _send_chat(url, headers, body)


def _send_chat(url: str, headers: dict, body: dict) -> LLMResult:
    """POST a chat request with rate-limit retries and map every failure to an error category."""

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = httpx.post(url, headers=headers, json=body, timeout=settings.llm_timeout_s)
        except httpx.TimeoutException as exc:
            raise LLMTimeout(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise LLMError(type(exc).__name__) from exc
        if resp.status_code != 429 or attempt == MAX_RETRIES:
            break
        time.sleep(_retry_wait(resp, attempt))  # rate limited: wait, then try again

    if resp.status_code == 429:
        raise LLMQuota("rate limit / quota exceeded after retries")
    if resp.status_code >= 400:
        err = LLMError(f"http_{resp.status_code}")
        err.category = f"http_{resp.status_code}"
        raise err
    try:
        body = resp.json()
        text = body["choices"][0]["message"]["content"]
        usage = body.get("usage") or {}
    except (ValueError, KeyError, IndexError) as exc:
        raise LLMMalformed("unexpected provider payload") from exc
    return LLMResult(text=text, model=settings.model_label,
                     input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"))



def vision_transcribe(image: bytes, mime: str) -> LLMResult:
    """Read a scanned page with the Azure OpenAI chat deployment (multimodal), returning plain text."""
    import base64
    sim = settings.simulate_failure
    if sim == "timeout":
        raise LLMTimeout("simulated provider timeout")
    if sim == "quota":
        raise LLMQuota("simulated quota exceeded")
    if settings.llm_provider != "azure":
        raise LLMError("vision OCR needs LLM_PROVIDER=azure with a vision-capable chat deployment")
    data_url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
    body: dict = {"messages": [
        {"role": "system", "content": VISION_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": "Transcribe this scanned insurance document."},
            {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
        ]},
    ]}
    if settings.llm_temperature.strip():
        body["temperature"] = float(settings.llm_temperature)
    url = _azure_url(settings.azure_openai_chat_deployment, "chat/completions")
    return _send_chat(url, {"api-key": settings.azure_openai_api_key}, body)


VISION_PROMPT = """You are an OCR engine. Transcribe all text in the image exactly as printed, line by line,
keeping the original order, labels, numbers, dates and spelling. Do not summarise, correct, translate or add
anything. Write [unreadable] for any part you cannot read. Output only the transcribed text."""


def embed(texts: list[str]) -> list[list[float]]:
    """Turn texts into embedding vectors with the Azure OpenAI embedding deployment (used for RAG)."""
    url = _azure_url(settings.azure_openai_embedding_deployment, "embeddings")
    try:
        resp = httpx.post(url, headers={"api-key": settings.azure_openai_api_key},
                          json={"input": texts}, timeout=settings.llm_timeout_s)
    except httpx.TimeoutException as exc:
        raise LLMTimeout(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise LLMError(type(exc).__name__) from exc
    if resp.status_code == 429:
        raise LLMQuota("embedding rate limit / quota exceeded")
    if resp.status_code >= 400:
        err = LLMError(f"http_{resp.status_code}")
        err.category = f"http_{resp.status_code}"
        raise err
    try:
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]
    except (ValueError, KeyError) as exc:
        raise LLMMalformed("unexpected embedding payload") from exc
