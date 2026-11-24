"""OCR for scanned uploads. Offline: the Azure calls are replaced with fakes."""
import httpx
import pytest

from app.config import settings
from app.services import llm, ocr
from tests.test_api import DOC, make_claim

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"


def upload_bytes(client, cid, data, name, mime, doc_type="INVOICE"):
    return client.post(f"/claims/{cid}/documents", data={"doc_type": doc_type}, files={"file": (name, data, mime)})


@pytest.fixture
def vision(monkeypatch):
    """Pretend Azure vision is configured and returns the invoice text."""
    monkeypatch.setattr(settings, "llm_provider", "azure")
    monkeypatch.setattr(settings, "azure_openai_chat_deployment", "gpt-4.1-mini")
    monkeypatch.setattr(settings, "azure_docintel_endpoint", "")
    monkeypatch.setattr(llm, "vision_transcribe", lambda data, mime: llm.LLMResult(text=DOC, model="azure:gpt-4.1-mini"))


def test_engine_choice(monkeypatch):
    monkeypatch.setattr(settings, "ocr_provider", "auto")
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "azure_docintel_endpoint", "")
    assert ocr.engine() is None
    monkeypatch.setattr(settings, "llm_provider", "azure")
    monkeypatch.setattr(settings, "azure_openai_chat_deployment", "gpt-4.1-mini")
    assert ocr.engine() == "vision"
    monkeypatch.setattr(settings, "azure_docintel_endpoint", "https://di.cognitiveservices.azure.com")
    monkeypatch.setattr(settings, "azure_docintel_api_key", "k")
    assert ocr.engine() == "docintel"            # auto prefers Document Intelligence once it is set up
    monkeypatch.setattr(settings, "ocr_provider", "vision")
    assert ocr.engine() == "vision"              # but it can be forced


def test_image_upload_without_ocr_is_rejected_and_logged(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "azure_docintel_endpoint", "")
    cid = make_claim(client)
    r = upload_bytes(client, cid, PNG, "scan.png", "image/png")
    assert r.status_code == 422 and "not configured" in r.json()["detail"]
    runs = client.get("/observability/runs", params={"claim_id": cid}).json()
    assert runs[0]["task"] == "OCR" and runs[0]["status"] == "FAILED"


def test_scan_is_read_then_processed_like_text(client, vision, monkeypatch):
    cid = make_claim(client)
    r = upload_bytes(client, cid, PNG, "invoice-photo.png", "image/png")
    assert r.status_code == 201, r.text
    assert r.json()["ocr_engine"] == "vision:gpt-4.1-mini"
    doc = client.get(f"/documents/{r.json()['document_id']}").json()
    assert "INV" in doc["text"] or doc["text"] == DOC
    monkeypatch.setattr(settings, "llm_provider", "mock")    # extraction offline from here
    body = client.post(f"/claims/{cid}/process").json()
    assert body["risk_level"] is not None
    runs = client.get("/observability/runs", params={"claim_id": cid}).json()
    assert {"OCR", "EXTRACTION"} <= {x["task"] for x in runs}


def test_scanned_pdf_needs_document_intelligence(client, vision):
    from pypdf import PdfWriter
    import io
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)  # a PDF page with no text layer, like a scan
    buf = io.BytesIO()
    w.write(buf)
    cid = make_claim(client)
    r = upload_bytes(client, cid, buf.getvalue(), "scan.pdf", "application/pdf")
    assert r.status_code == 422


def test_document_intelligence_flow(monkeypatch):
    """Submit, poll, and read analyzeResult.content: ready for when the resource is created."""
    monkeypatch.setattr(settings, "ocr_provider", "docintel")
    monkeypatch.setattr(settings, "azure_docintel_endpoint", "https://di.cognitiveservices.azure.com/")
    monkeypatch.setattr(settings, "azure_docintel_api_key", "k")
    calls = []

    def fake_post(url, headers=None, content=None, timeout=None):
        calls.append(url)
        return httpx.Response(202, headers={"operation-location": "https://di/op/1"})
    polls = iter([{"status": "running"}, {"status": "succeeded", "analyzeResult": {"content": "INVOICE\nTotal: 100"}}])
    monkeypatch.setattr(ocr.httpx, "post", fake_post)
    monkeypatch.setattr(ocr.httpx, "get", lambda url, headers=None, timeout=None: httpx.Response(200, json=next(polls)))
    monkeypatch.setattr(ocr.time, "sleep", lambda s: None)
    res = ocr.read(PNG, "image/png")
    assert res.engine == "docintel" and "Total: 100" in res.text
    assert "prebuilt-read:analyze" in calls[0] and "api-version=2024-11-30" in calls[0]
