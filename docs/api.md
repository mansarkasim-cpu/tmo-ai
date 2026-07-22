# API Reference (Ringkas)

Base: `http://<host>:<port>`

1) Upload PDF
- `POST /upload`
- Form: `file` (PDF)
- Response (201/200):
```json
{
  "document_id": "...",
  "filename": "...",
  "file_type": "pdf",
  "pages": 130,
  "size": 123456,
  "status": "uploaded",
  "message": "Document uploaded successfully"
}
```

2) List documents
- `GET /documents`
- Response: list document metadata (id, filename, pages)

3) Get document detail
- `GET /documents/{document_id}`
- Response: full text and metadata

4) Chat (Agent)
- `POST /chat`
- Body: `{"message":"...","document_id": null|id}`
- Response: `{"response":"...","document_id":null}`
- Behavior: runs the LangGraph-style agent which can call KB or SQL tools.

5) KB endpoints
- `POST /kb/index/{document_id}` — indeks dokumen ke KB.
- `GET /kb/search?q=...&k=4` — cari top-k chunks.

6) SQL Query
- `POST /sql/query`
- Body: `{"query":"SELECT ...", "params":[], "max_rows":100, "readonly":true}`
- Response: `{"rows":[...], "columns":[...], "rowcount": N}`

Notes
- Semua endpoint saat ini tidak memerlukan autentikasi — tambahkan auth untuk produksi.
- KB indexing dilakukan otomatis saat upload; juga tersedia endpoint manual untuk reindex.

