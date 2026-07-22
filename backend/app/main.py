from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.upload import router as upload_router
from app.api.documents import router as documents_router
from app.api.kb import router as kb_router
from app.api.sql import router as sql_router
from app.services.sql_service import init_db

app = FastAPI(
    title="TMO-AI",
    version="0.1.0",
    # Expose API docs under the proxied `/api` path so the browser
    # (served from the same origin) doesn't attempt to access loopback
    # addresses and to keep docs colocated with the API path.
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

# Allow the frontend (served from a different origin/port) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(documents_router)
app.include_router(kb_router)
app.include_router(sql_router)


@app.on_event("startup")
def startup_event():
    # ensure DB tables exist
    try:
        init_db()
    except Exception:
        # best-effort: avoid crashing startup for DB issues here
        pass


@app.get("/")
def root():

    return {
        "name": "TMO-AI",
        "status": "running"
    }