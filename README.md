# Rekap Keuangan Al Husnayain

Aplikasi web sederhana untuk merekap keuangan sekolah: pemasukan & pengeluaran,
data siswa, pembayaran SPP, dan laporan bulanan.

Dibuat dengan **Python (Flask)**. Database bisa memakai **SQLite lokal**
(ringan, tanpa konfigurasi) atau **Supabase/PostgreSQL** agar data tersinkron
antar perangkat dan bisa diakses dari mana saja.

## Fitur

- Login admin/bendahara + ganti password
- Dashboard ringkasan saldo, tren 6 bulan, dan capaian SPP
- Catat pemasukan & pengeluaran (tambah, ubah, hapus, filter)
- Kelola kategori pemasukan/pengeluaran
- Kelola data siswa (NIS, nama, kelas, nominal SPP)
- Catat pembayaran SPP per bulan per siswa
- Laporan rekap bulanan per kategori + export CSV (bisa dibuka di Excel)
- **Cetak laporan** siap A4 (kop sekolah, logo, rincian transaksi, tanda tangan)
- **Pengaturan aplikasi**: ubah judul, logo, nama & alamat sekolah, nama
  kepala sekolah/bendahara, kota tanggal cetak
- Dukungan database **Supabase/PostgreSQL** (sinkron antar perangkat)
- Backup database lokal + upload ke Google Drive (via rclone)
- Akses dari mana saja lewat Cloudflare Tunnel (HTTPS)
- Data contoh otomatis saat pertama kali dijalankan

## Akun default

| Username | Password |
|----------|----------|
| `admin`  | `admin123` |

> **Penting:** segera ganti password lewat menu **Ganti Password** di sidebar,
> terutama jika aplikasi diakses dari internet. Kunci sesi acak otomatis
> disimpan di file `.secret_key`.

## Cara menjalankan (cepat)

```bash
cd rekap-keuangan-sekolah
./start.sh      # menjalankan server di latar belakang
./status.sh     # cek status + alamat
./stop.sh       # menghentikan server
```

Lalu buka <http://localhost:5000>.

Alternatif manual:

```bash
pip install -r requirements.txt
python3 app.py
```

Database `keuangan.db` otomatis dibuat beserta data contoh. Untuk memulai dari
data kosong, hapus `keuangan.db` lalu jalankan ulang.

## Menyimpan database di Supabase (sinkron antar perangkat)

Aplikasi otomatis memakai Supabase jika variabel `DATABASE_URL` diisi; jika
tidak, tetap memakai SQLite lokal. Jadi data tersimpan langsung di Supabase
(bukan sekadar disalin) dan semua perangkat melihat data yang sama.

### 1. Buat proyek Supabase

1. Daftar/masuk ke <https://supabase.com>, buat proyek baru.
2. Buka **Project Settings → Database → Connection string**.
3. Pilih **Session pooler** (port `5432`) — lebih kompatibel dengan IPv4.
4. Salin string `postgresql://...` dan ganti `[YOUR-PASSWORD]` dengan password
   database proyek Anda.

### 2. Simpan connection string

```bash
cp .env.example .env
nano .env      # tempel DATABASE_URL=postgresql://...
```

> Jangan bagikan file `.env` (berisi password). File ini sudah diabaikan `.gitignore`.

### 3. Buat tabel & salin data lama (sekali saja)

```bash
python3 migrate_to_supabase.py
```

Skrip ini membuat tabel di Supabase dan menyalin seluruh data dari
`keuangan.db`. Gunakan `--replace` jika ingin mengosongkan target lalu salin
ulang.

### 4. Jalankan ulang aplikasi

```bash
./stop.sh && ./start.sh
./status.sh
```

Cek: dashboard menampilkan data yang sama. Setiap transaksi baru langsung
tersimpan ke Supabase.

Catatan:
- Tanpa koneksi internet, aplikasi tidak bisa memakai Supabase. Untuk mode
  offline, hapus/komentari `DATABASE_URL` di `.env` agar kembali ke SQLite.
- Backup lokal (`./backup.sh`) hanya relevan untuk mode SQLite. Untuk Supabase,
  gunakan fitur **Database Backups** bawaan Supabase.
- `pg8000` (driver PostgreSQL murni Python) sudah masuk `requirements.txt`.
- Koneksi langsung `db.<ref>.supabase.co` memakai **IPv6**. Jika nanti dijalankan
  di jaringan yang hanya IPv4, ganti `DATABASE_URL` dengan connection string
  **Session pooler** (port `5432`).
- Kecepatan akses tergantung jarak region proyek Supabase. Pilih region terdekat
  (mis. **Singapore**) saat membuat proyek agar lebih responsif.
- Aplikasi memakai connection pool (default 5 koneksi). Ubah dengan variabel
  `DB_POOL_SIZE` di `.env` bila perlu.
- Kredensial ada di `.env` (jangan dibagikan/di-commit). Jika password database
  pernah bocor, reset lewat **Project Settings → Database → Reset database password**
  lalu perbarui `.env`.

## Akses dari mana saja (login dari luar)

Gunakan Cloudflare Quick Tunnel — gratis, otomatis HTTPS, tanpa buka port router:

```bash
./start.sh        # pastikan server jalan
./tunnel.sh       # buka tunnel, tunggu sampai muncul "URL PUBLIK"
```

Akan muncul alamat seperti `https://xxxx-xxxx.trycloudflare.com`. Buka alamat
itu dari HP/laptop mana pun. Alamat tersimpan di `tunnel.url` (lihat `./status.sh`).

Catatan:
- `tunnel.sh` harus tetap berjalan selama butuh akses publik. Tutup dengan `Ctrl+C`.
- Alamat Quick Tunnel **berubah setiap kali dijalankan ulang**. Untuk alamat tetap,
  perlu akun Cloudflare (named tunnel) atau deploy ke VPS/hosting.
- Karena bisa diakses publik, **wajib ganti password** dan jangan bagikan URL.

## Backup ke Google Drive

Google Drive adalah penyimpanan file, bukan database. Jadi aplikasi **membuat
salinan database secara berkala lalu mengunggahnya** ke Drive — bukan menjalankan
database langsung di Drive (itu berisiko korup).

### 1. Siapkan rclone (sekali saja)

```bash
rclone config
```

Ikuti prompt:
- `n` (New remote)
- name: **gdrive**
- Storage: pilih **Google Drive** (ketik nomor `drive`)
- `client_id` / `client_secret`: kosongkan (Enter)
- scope: pilih `1` (Full access) atau `2` (Read-only)
- `Edit advanced config?`: `n`
- `Use auto config?`: `y` jika ada browser di perangkat ini; jika headless pilih `n`
  lalu buka URL yang diberikan di browser, login Google, izinkan akses, dan
  tempel kode/token yang diminta
- `Configure this as a Shared Drive?`: `n` (kecuali memakai shared drive)
- `y` untuk menyimpan

Cek: `rclone listremotes` harus menampilkan `gdrive:`.

### 2. Jalankan backup

```bash
./backup.sh
```

Backup lokal disimpan di folder `backups/` (maksimal 30 file terbaru) dan
diunggah ke `gdrive:RekapKeuanganSekolah/`.

### 3. Backup otomatis berkala

```bash
BACKUP_INTERVAL=3600 ./backup-daemon.sh start   # tiap 1 jam
./backup-daemon.sh status
./backup-daemon.sh stop
```

Ubah folder tujuan / nama remote bila perlu:

```bash
GDRIVE_REMOTE=gdrive GDRIVE_DIR=BackupSekolah ./backup.sh
```

### Restore

Unduh file `keuangan-*.db` dari Google Drive, lalu ganti `keuangan.db` dengan
file tersebut (hentikan server dulu dengan `./stop.sh`).

## Deploy gratis dengan alamat tetap (tanpa domain)

Agar aplikasi punya alamat permanen seperti `https://rekap-keuangan-al-husnayain.onrender.com`
tanpa perlu menyalakan server/tunnel, deploy ke hosting gratis. Database tetap di
Supabase. File `Procfile`, `wsgi.py`, dan `render.yaml` sudah disiapkan.

### Opsi A — Render (gratis)

1. Unggah proyek ini ke GitHub (repo **private** boleh).
   Pastikan `.env` **tidak** ikut terunggah (sudah ada di `.gitignore`).
2. Daftar di <https://render.com> lalu **New → Web Service**, hubungkan repo.
3. Render akan membaca `render.yaml`. Jika mengisi manual:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
4. Tambahkan **Environment Variables**:
   - `DATABASE_URL` = connection string Supabase (Session pooler disarankan)
   - `SECRET_KEY` = string acak panjang (atau biarkan dibuat otomatis)
   - `DB_POOL_SIZE` = `3`
5. Deploy. Buka URL `*.onrender.com` yang diberikan.

> Catatan: paket gratis Render tidur setelah tidak dipakai; akses pertama bisa
> lambat (~30 detik) lalu normal. Logo disimpan di database (bukan file), jadi
> tetap ada setelah restart/redeploy.

### Opsi B — PythonAnywhere (gratis)

1. Daftar di <https://www.pythonanywhere.com>, buka **Web → Add a new web app**.
2. Pilih **Flask**, lalu arahkan ke folder proyek.
3. Di **WSGI configuration file**, isi:
   ```python
   import sys
   sys.path.insert(0, "/home/USERNAME/rekap-keuangan-sekolah")
   from wsgi import application
   ```
4. Buat virtualenv dan pasang dependensi:
   ```bash
   mkvirtualenv rekap --python=python3.12
   pip install -r requirements.txt
   ```
5. Isi `DATABASE_URL` (dan `SECRET_KEY`) lewat file `.env` di folder proyek.
6. Klik **Reload**. Alamatnya `https://USERNAME.pythonanywhere.com`.

### Setelah deploy

- Ganti password admin default.
- Buka **Pengaturan** untuk mengisi judul, logo, dan data sekolah.
- Uji **Laporan → Cetak** lalu pilih *Simpan sebagai PDF*.

## Struktur proyek

```
rekap-keuangan-sekolah/
├── app.py              # Rute & logika aplikasi
├── db.py               # Skema database (SQLite/Postgres), koneksi, data contoh
├── settings_store.py   # Pengaturan aplikasi (judul, logo, dll) + cache
├── migrate_to_supabase.py  # Salin data lokal ke Supabase
├── wsgi.py             # Entry point WSGI (gunicorn/PythonAnywhere)
├── Procfile            # Perintah start untuk hosting (Render/Heroku)
├── render.yaml         # Blueprint deploy Render
├── .env.example        # Contoh konfigurasi DATABASE_URL
├── start.sh            # Jalankan server (background)
├── stop.sh             # Hentikan server
├── status.sh           # Cek status & alamat
├── tunnel.sh           # Akses publik via Cloudflare Tunnel
├── backup.sh           # Backup database + upload Google Drive
├── backup-daemon.sh    # Backup otomatis berkala
├── requirements.txt
├── templates/          # Halaman HTML (Jinja2)
│   └── report_print.html   # Tampilan cetak laporan (A4)
└── static/             # CSS, JavaScript, dan logo bawaan
    └── img/logo.svg
```

## Catatan

- Pembayaran SPP disimpan terpisah dari transaksi umum. Jika ingin SPP masuk
  ke saldo kas, tambahkan juga transaksi pemasukan dengan kategori "SPP".
- Mode database dipilih otomatis: `DATABASE_URL` terisi → Supabase/PostgreSQL,
  kosong → SQLite lokal.
