import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.upload import UploadResponse
from app.services.pdf_service import MAX_FILE_SIZE, parse_pdf, save_document, summarize_text
from app.services.kb_service import kb

router = APIRouter()
logger = logging.getLogger("tmo_ai.upload")


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File size exceeds 50 MB limit")

    text, num_pages = parse_pdf(content)
    summary = summarize_text(text)
    doc_id = save_document(text, filename=file.filename, pages=num_pages, summary=summary)

    # Try to index into KB; failures shouldn't break upload. Indexing is internal.
    try:
        kb.index_document(doc_id)
    except Exception:
        logger.exception("Failed to index document %s into KB", doc_id)

    size = len(content)
    file_type = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''

    message = "Document uploaded successfully"
    if not text.strip():
        message = (
            "Document uploaded, but no text could be extracted (the PDF may be a "
            "scanned image without a text layer). Content-based Q&A will not work "
            "for this document."
        )

    return UploadResponse(
        document_id=doc_id,
        filename=file.filename,
        file_type=file_type,
        pages=num_pages,
        size=size,
        status="uploaded",
        message=message,
    )
