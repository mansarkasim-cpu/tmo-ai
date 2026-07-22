# Agent (LangGraph-style)

Deskripsi
- Agent diimplementasikan sebagai loop yang dipicu oleh LLM (ChatOllama). Agent meminta LLM untuk mengeluarkan aksi dalam format JSON, mis. `{"action":"kb_search","query":"...","k":4}`.
- Tool yang tersedia saat ini:
  - `kb_search`: memanggil `kb.search(query, k)` dan mengembalikan potongan dokumen dengan metadata.
  - `sql_query`: memanggil `execute_query(query)` pada SQLite (readonly default).

Protokol JSON
- Aksi valid: `kb_search`, `sql_query`, `final`.
- `kb_search` → balik: `{"kb_results": [...]}`
- `sql_query` → balik: `{"rows": [...], "columns": [...]}`
- `final` → laporkan jawaban: `{"action":"final","answer":"..."}`

Alur loop
1. Kirim prompt sistem yang menjelaskan tools dan format JSON.
2. LLM merespon JSON tindakan.
3. Agent mengeksekusi tindakan, mengemas hasil sebagai `TOOL_RESULT`, dan mengembalikan semuanya ke LLM untuk langkah berikutnya.
4. Ulang sampai LLM mengembalikan `final`.

Catatan implementasi
- Parser JSON sederhana; jika output LLM bukan JSON, agent meminta model untuk memperbaiki (retry).
- Batas langkah (`max_steps`) untuk mencegah loop tak berujung.
- Hasil tool disisipkan sebagai JSON string ke prompt agar LLM bisa menggunakannya.

Pertimbangan keamanan
- Batasi akses SQL ke readonly kecuali diizinkan.
- Buat otorisasi/role untuk endpoint agent jika diekspos.

Perluasan rekomendasi
- Integrasi LangGraph resmi bila membutuhkan fitur workflow lebih lengkap.
- Tambah tool: file retrieval, external API, user profiling, atau write-to-db (dengan otorisasi).