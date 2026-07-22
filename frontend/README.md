# TMO-AI Frontend

UI chat sederhana (HTML/CSS/JS, tanpa build step) untuk backend TMO-AI.

## Fitur
- Kirim pesan ke `/chat` dan tampilkan balasan AI.
- Sidebar riwayat chat (`GET /chats`, dengan pagination di backend).
- Sidebar memories (`GET /memories`) + form untuk menambah memory (`POST /memories`).
- Field "API URL" untuk mengganti alamat backend tanpa edit kode.

## Menjalankan

1. Jalankan backend terlebih dahulu (dari folder `backend`):
   ```powershell
   cd d:\Project\tmo-ai\backend
   uvicorn app.main:app --reload
   ```
   Backend sudah dikonfigurasi dengan CORS terbuka (`*`) sehingga bisa diakses dari origin manapun.

2. Buka frontend, pilih salah satu:
   - **Buka langsung**: klik dua kali `index.html` (atau buka lewat `file://` di browser).
   - **Serve statis** (disarankan agar fetch lebih konsisten):
     ```powershell
     cd d:\Project\tmo-ai\frontend
     python -m http.server 5173
     ```
     Lalu buka `http://localhost:5173` di browser.

3. Di UI, pastikan kolom **API URL** menunjuk ke alamat backend, contoh `http://localhost:8000`.

## Catatan
- Tidak ada dependency/build tool — murni HTML/CSS/JS agar cepat dijalankan.
- Jika backend dijalankan di host/port berbeda, cukup ubah nilai di kolom "API URL" pada sidebar.
