# Arsitektur Sistem TMO-AI

Tujuan: ringkasan tinggi-tahap bagaimana komponen backend, KB, agent, dan DB saling berinteraksi.

Komponen utama
- API (FastAPI): menerima upload, chat, dokumen, KB dan SQL query.
- Upload service: menerima PDF, ekstrak teks (pypdf), menyimpan ke store in-memory (pdf_service.save_document).
- Knowledge Base (KB): embedding + vector store. Implementasi: prefer LangChain/FAISS, fallback ke numpy-based SimpleVectorStore.
- Agent (LangGraph-style): loop LLM yang memilih aksi (kb_search, sql_query, final). LLM: ChatOllama adapter.
- Database: SQLite untuk data tabular dan query melalui `/sql/query` API.

Alur utama
1. Upload PDF -> `pdf_service` ekstrak teks & summary, simpan dokumen -> otomatis index ke KB (background-like, internal).
2. Pengguna memanggil `/chat` -> `chat` endpoint mengambil dokumen context (opsional) -> panggil `ask_ai()` agent.
3. Agent: LLM mengeluarkan aksi JSON -> agent menjalankan tool (KB search atau SQL query) -> kembalikan hasil ke LLM -> ulang sampai `final`.
4. User menerima jawaban yang dihasilkan agent.

Pertimbangan deployment
- Pastikan model embeddings (`sentence-transformers`) dan dependency FAISS/numPy terpasang.
- Untuk produksi, sarankan menggunakan FAISS/Annoy milik produksi dan simpan index ke disk.
- Gunakan env var `TMO_AI_DB_PATH` untuk menunjuk file SQLite persistent.

Diagram ringkas (teks)
User -> FastAPI -> (Upload | Chat | Documents | SQL | KB)
Upload -> pdf_service -> save_document -> kb.index_document
Chat -> chat_service.agent -> (kb.search | sql_service.execute_query) -> LLM -> response

