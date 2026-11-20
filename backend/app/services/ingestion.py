"""Document ingestion: size/type checks, hashing (for duplicate detection) and text extraction."""
import hashlib
import io

from pypdf import PdfReader

ALLOWED = {".txt", ".pdf", ".md"}


class IngestionError(ValueError):
    pass


def extract_text(filename: str, data: bytes, max_bytes: int) -> tuple[str, str]:
    if not data:
        raise IngestionError("empty file")
    if len(data) > max_bytes:
        raise IngestionError("file too large")
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED:
        raise IngestionError(f"unsupported file type '{ext}' (allowed: {', '.join(sorted(ALLOWED))})")
    sha = hashlib.sha256(data).hexdigest()
    if ext == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as exc:
            raise IngestionError("could not read PDF") from exc
    else:
        text = data.decode("utf-8", errors="replace")
    if not text.strip():
        raise IngestionError("no extractable text (scanned images need OCR, planned post-MVP)")
    return text, sha
