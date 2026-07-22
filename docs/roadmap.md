# Roadmap

Prioritas jangka pendek
- Tambah logging dan monitoring untuk indexing KB (success / failure counts).
- Tambah otentikasi untuk endpoint `/sql/query` dan `/chat`.
- Tambah batch indexer CLI untuk mengindeks semua dokumen yang sudah ada.

Prioritas menengah
- Pindahkan storage dokumen dari in-memory ke persistent (filesystem atau object storage).
- Simpan dan muat index FAISS ke/dari disk untuk startup lebih cepat.
- Integrasi LangGraph / RAG framework resmi bila diperlukan.

Prioritas jangka panjang
- Horizontal scaling: pindahkan vectorstore ke layanan terdistribusi (Milvus, Weaviate, Pinecone).
- Pipeline ingestion yang resilien: worker queue, retries, backoff.
- Observability: metrics (Prometheus), traces (OpenTelemetry), dan logs terpusat.

Tasks implementasi yang direkomendasikan
- Unit/integration tests untuk upload, indexing, chat-agent flows.
- CI pipeline yang meng-install dependencies penting (sentence-transformers, faiss).
- Dokumentasi runbook untuk deploy (env vars, resource requirements).

