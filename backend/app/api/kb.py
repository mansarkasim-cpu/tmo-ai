from fastapi import APIRouter, HTTPException, Query

from app.services.kb_service import kb
from app.services.pdf_service import get_document

router = APIRouter()


@router.post("/kb/index/{document_id}")
def index_document(document_id: str, chunk_size: int = 500, overlap: int = 50):
    # verify document exists
    if get_document(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        res = kb.index_document(document_id, chunk_size=chunk_size, overlap=overlap)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return res


@router.get("/kb/search")
def kb_search(q: str = Query(..., alias="q"), k: int = 4):
    try:
        results = kb.search(q, k=k)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"query": q, "results": results}
