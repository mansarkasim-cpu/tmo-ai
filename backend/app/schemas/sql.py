from typing import Any, List, Optional
from pydantic import BaseModel


class SQLQueryRequest(BaseModel):
    query: str
    params: Optional[List[Any]] = None
    max_rows: Optional[int] = 100
    readonly: Optional[bool] = True


class SQLQueryRow(BaseModel):
    values: dict


class SQLQueryResponse(BaseModel):
    rows: List[dict]
    columns: List[str]
    rowcount: int
    message: Optional[str] = None
