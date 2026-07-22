import uuid
from io import BytesIO
from pypdf import PdfReader
import re

# In-memory store: {document_id: {text, filename, pages}}
_document_store: dict[str, dict] = {}

# Allow files up to 50 MB
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def parse_pdf(file_bytes: bytes) -> tuple[str, int]:
    """Extract text and page count from PDF bytes."""
    reader = PdfReader(BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages), len(reader.pages)


def summarize_text(text: str, max_chars: int = 1000) -> str:
    """Create a lightweight extractive summary by taking the first
    `max_chars` characters and trimming to the last sentence boundary.
    This is fast and avoids additional LLM calls during upload.
    """
    if not text:
        return ""
    t = text.strip()
    if len(t) <= max_chars:
        return t
    # try to cut at the last period before max_chars
    cut = t.rfind('.', 0, max_chars)
    if cut == -1:
        cut = max_chars
    summary = t[: cut + 1].strip()
    if len(summary) == 0:
        summary = t[:max_chars].strip()
    if len(summary) < len(t):
        summary = summary.rstrip() + " ..."
    return summary


def save_document(text: str, filename: str | None = None, pages: int | None = None, summary: str | None = None) -> str:
    doc_id = str(uuid.uuid4())
    if summary is None:
        summary = summarize_text(text)
    _document_store[doc_id] = {
        "text": text,
        "filename": filename,
        "pages": pages,
        "summary": summary,
    }
    return doc_id


def get_document(doc_id: str) -> str | None:
    entry = _document_store.get(doc_id)
    if entry is None:
        return None
    return entry.get("text")


def get_summary(doc_id: str) -> str | None:
    entry = _document_store.get(doc_id)
    if entry is None:
        return None
    return entry.get("summary")


def get_metadata(doc_id: str) -> dict | None:
    entry = _document_store.get(doc_id)
    if entry is None:
        return None
    return {"filename": entry.get("filename"), "pages": entry.get("pages")}


def list_documents() -> list[dict]:
    """Return a list of stored documents with id, filename and pages."""
    out = []
    for doc_id, entry in _document_store.items():
        out.append({"document_id": doc_id, "filename": entry.get("filename"), "pages": entry.get("pages")})
    return out


def find_best_document(query: str) -> str | None:
    """Return the document_id whose text has the highest simple token overlap with `query`.

    This is a lightweight heuristic: tokenize on word characters, lowercase, and pick
    the document with the largest intersection size. Returns None if no documents
    or no overlap found.
    """
    if not query:
        return None

    tokens = set(re.findall(r"\w+", query.lower()))
    if not tokens:
        return None

    best_id = None
    best_score = 0

    for doc_id, entry in _document_store.items():
        text = entry.get("text") or ""
        doc_tokens = set(re.findall(r"\w+", text.lower()))
        score = len(tokens & doc_tokens)
        if score > best_score:
            best_score = score
            best_id = doc_id

    return best_id if best_score > 0 else None
