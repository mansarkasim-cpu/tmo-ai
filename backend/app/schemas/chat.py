from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    document_id: Optional[str] = None
    model: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    document_id: Optional[str] = None


class ChatRecord(BaseModel):
    id: int
    message: str
    response: str
    document_id: Optional[str] = None
    created_at: str


class ChatsList(BaseModel):
    items: list[ChatRecord]
    total: int
    page: int
    page_size: int


class MemoryRequest(BaseModel):
    key: Optional[str] = None
    value: str


class MemoryRecord(BaseModel):
    id: int
    key: Optional[str] = None
    value: str
    created_at: str


class MemoriesList(BaseModel):
    items: list[MemoryRecord]
    total: int = 0