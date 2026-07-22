# Knowledge Base (KB)

Tujuan
- Menyediakan retrieval berbasis embedding untuk dokumen yang di-upload.

Desain
- Dokumen disimpan secara sederhana di `pdf_service` (in-memory store) sebagai teks penuh dan ringkasan.
- Saat upload, service mencoba mengindeks dokumen ke KB otomatis.
- KB menggunakan embedding dari `sentence-transformers` (default model: `all-MiniLM-L6-v2`). Jika `langchain` tersedia, gunakan `HuggingFaceEmbeddings`.
- Vector store: prefer `FAISS` via LangChain; fallback ke `SimpleVectorStore` berbasis NumPy untuk lingkungan tanpa LangChain/FAISS.

Chunking
- Teks dipotong menjadi chunk (default 500 chars, overlap 50) sebelum embedding.
- Setiap chunk menyimpan metadata `document_id` dan `chunk` index.

API terkait
- `POST /kb/index/{document_id}` — indeks dokumen tertentu.
- `GET /kb/search?q=...&k=4` — cari top-k chunk relevan.

Persistensi
- Saat ini index fallback bersifat in-memory. Untuk produksi, simpan index FAISS ke disk dan muat ulang saat startup.

Skalabilitas
- Untuk dataset besar, gunakan batching embedding, background worker (Celery/RQ), dan penyimpanan index terdistribusi (Milvus, FAISS on disk, or Pinecone/Weaviate).

Catatan operasional
- Pastikan GPU / resource untuk model embedding jika memproses banyak dokumen.
- Pertimbangkan TTL, versi dokumen, dan strategi reindexing saat dokumen diperbarui atau dihapus.