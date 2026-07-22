from fastapi import APIRouter, HTTPException

from app.services.pdf_service import list_documents, get_document, get_metadata
from app.schemas.document import DocumentInfo, DocumentDetail

router = APIRouter()


@router.get("/documents", response_model=list[DocumentInfo])
def documents_list():
    docs = list_documents()
    return [DocumentInfo(**d) for d in docs]


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def documents_get(document_id: str):
    text = get_document(document_id)
    meta = get_metadata(document_id)
    if text is None or meta is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentDetail(document_id=document_id, filename=meta.get("filename"), pages=meta.get("pages"), text=text)
