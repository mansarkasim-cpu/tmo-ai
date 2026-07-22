from pydantic import BaseModel


class DocumentInfo(BaseModel):
    document_id: str
    filename: str | None = None
    pages: int | None = None


class DocumentDetail(BaseModel):
    document_id: str
    filename: str | None = None
    pages: int | None = None
    text: str
