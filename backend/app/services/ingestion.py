"""Document ingestion: size/type checks, hashing (for duplicate detection) and text extraction.
Images and scanned PDFs have no text layer, so they raise NeedsOCR and the OCR step reads them."""
import hashlib
import io

from pypdf import PdfReader

TEXT_TYPES = {".txt", ".pdf", ".md"}
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
ALLOWED = TEXT_TYPES | set(IMAGE_TYPES)


class IngestionError(ValueError):
    pass


class NeedsOCR(Exception):
    """The file is valid but has no text layer: a photo/scan, or a PDF made of scanned pages."""
    def __init__(self, sha: str, mime: str):
        super().__init__("needs OCR")
        self.sha, self.mime = sha, mime


def extract_text(filename: str, data: bytes, max_bytes: int) -> tuple[str, str]:
    if not data:
        raise IngestionError("empty file")
    if len(data) > max_bytes:
        raise IngestionError("file too large")
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED:
        raise IngestionError(f"unsupported file type '{ext}' (allowed: {', '.join(sorted(ALLOWED))})")
    sha = hashlib.sha256(data).hexdigest()
    if ext in IMAGE_TYPES:
        raise NeedsOCR(sha, IMAGE_TYPES[ext])
    if ext == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as exc:
            raise IngestionError("could not read PDF") from exc
        if not text.strip():
            raise NeedsOCR(sha, "application/pdf")
    else:
        text = data.decode("utf-8", errors="replace")
    if not text.strip():
        raise IngestionError("no extractable text")
    return text, sha
