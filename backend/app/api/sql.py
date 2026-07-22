from fastapi import APIRouter, HTTPException
from app.schemas.sql import SQLQueryRequest, SQLQueryResponse
from app.services.sql_service import execute_query

router = APIRouter()


@router.post("/sql/query", response_model=SQLQueryResponse)
def run_sql(req: SQLQueryRequest):
    try:
        rows, cols = execute_query(req.query, params=req.params, max_rows=req.max_rows or 100, readonly=req.readonly if req.readonly is not None else True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return SQLQueryResponse(rows=rows, columns=cols, rowcount=len(rows), message="OK")
