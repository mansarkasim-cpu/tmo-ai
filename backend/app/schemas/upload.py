from pydantic import BaseModel


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    file_type: str
    pages: int
    size: int
    status: str
    message: str
