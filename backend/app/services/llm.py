"""Hosted-model client (OpenAI-compatible: Groq or Gemini) plus an offline mock.
All provider errors are mapped to a small set of categories used in traces and metrics."""
import json
import re
import time
from dataclasses import dataclass

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


def _mock_extract(document_text: str) -> str:
    """Deterministic 'Label: value' parser that returns the same JSON shape as the real model."""
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

    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY not configured")
    try:
        resp = httpx.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system_prompt},
                             {"role": "user", "content": user_prompt}],
            },
            timeout=settings.llm_timeout_s,
        )
    except httpx.TimeoutException as exc:
        raise LLMTimeout(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise LLMError(type(exc).__name__) from exc
    if resp.status_code == 429:
        raise LLMQuota("rate limit / quota exceeded")
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
