# Database

Konfigurasi
- DB default: SQLite in-memory (`:memory:`).
- Untuk persistence, set environment variable `TMO_AI_DB_PATH` ke path file SQLite sebelum menjalankan server.
  - Contoh (PowerShell):
    ```powershell
    $env:TMO_AI_DB_PATH = "D:\Project\tmo-ai\database\data.sqlite"
    uvicorn app.main:app --reload
    ```

Service SQL
- Endpoint: `POST /sql/query` (lihat `app.api.sql`).
- Payload: `{"query":"SELECT ...", "params": [], "max_rows": 100, "readonly": true}`.
- Batasan:
  - `readonly=True` hanya mengizinkan `SELECT` dan `PRAGMA`.
  - Hanya satu statement per request.
  - Hasil dibatasi oleh `max_rows`.

Inisialisasi DB contoh
- Buat file SQLite dan tabel contoh:
```bash
sqlite3 data.sqlite "CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT, email TEXT);"
sqlite3 data.sqlite "INSERT INTO users(name,email) VALUES('Alice','a@example.com'),('Bob','b@example.com');"
```

Keamanan & Operasional
- Endpoint SQL saat ini tidak memiliki autentikasi: tambahkan auth sebelum produksi.
- Batasi akses query sensitif, dan audit queries yang dijalankan.
- Pertimbangkan migrasi ke RDBMS yang lebih kuat (Postgres) bila diperlukan.