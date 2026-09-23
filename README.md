# NGG Attendance

Sistem manajemen kehadiran & race pack pickup untuk event **Momaz Next-Gen Grow (NGG) Fun Walk Oct 2026**.

## Arsitektur

```
┌─────────────────────────────────────────────────────────────┐
│                     LOCAL DEVELOPMENT                        │
│  Google Sheets → SQLite (local) → sync push → GSheets       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  PRODUCTION (VERCEL + NEON)                  │
│  Google Sheets → Neon PostgreSQL → sync push → GSheets      │
└─────────────────────────────────────────────────────────────┘
```

- **SQLite** untuk local development (zero config, fast)
- **Neon PostgreSQL** untuk production di Vercel (persistent, scalable)
- **Google Sheets** sebagai source of truth / backup
- Auto-detect: jika `DATABASE_URL` ada → pakai Neon, jika tidak → pakai SQLite
- Race condition dihilangkan via atomic conditional UPDATE (cek status + tulis dalam satu statement)
- Sync dari Google Sheets hanya dijalankan saat database kosong (tidak menimpa data yang sudah ada)
- Push balik ke Google Sheets: **sinkron dengan retry (3×)** di Vercel (BackgroundTasks serverless tidak selalu selesai), async via BackgroundTasks di local
- **Login multi-akun** (admin/staff): cookie HttpOnly session, password hash scrypt (min 8 karakter), lockout 5 gagal → 15 menit, rate limit per-IP (30/menit default → HTTP 429)
- **Audit log** ditulis dalam transaksi yang sama dengan setiap aksi tulis (check-in, absen, undo, user, login)
- **Swagger/ReDoc/OpenAPI dimatikan di production** (`api/index.py`), aktif hanya di local dev (`main.py`)
- **Global exception handler** + request logging (method, path, status, duration)
- **CI**: GitHub Actions menjalankan `ruff check` + `pytest` di setiap push/PR

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Uvicorn |
| Database (Local) | SQLite3 (WAL mode) |
| Database (Production) | Neon PostgreSQL |
| External | Google Sheets API (gspread) |
| Frontend | HTML + Bootstrap 5 + Vanilla JS |
| Hosting | Vercel (serverless) |

## Setup (Local Development)

### 1. Clone & Install

```bash
git clone https://github.com/your-repo/ngg-attendance.git
cd ngg-attendance
pip install -r requirements.txt
```

### 2. Setup Google Service Account

1. Buka [Google Cloud Console](https://console.cloud.google.com/)
2. Buat Service Account baru
3. Generate JSON key → simpan sebagai `auth-xxx.json` di root project
4. Share Google Sheets ke email service account (`api-xxx@xxx.iam.gserviceaccount.com`) dengan role **Editor**

### 3. Environment Variables

Buat file `.env` di root project (salin dari `.env.example`):

```bash
cp .env.example .env
```

```env
SPREADSHEET_NAME=NGG Fun Walk Oct 2026 - Data Peserta (PAID)
CREDENTIALS_FILE=auth-xxx.json
SESSION_TTL_HOURS=12
LOGIN_MAX_FAILURES=5
LOGIN_LOCK_MINUTES=15
LOGIN_RATE_LIMIT=30
LOGIN_RATE_WINDOW_SECONDS=60
```

**User admin dibuat manual** (tidak ada auto-seed). Generate hash password lalu insert via SQL:

```bash
python scripts/hash_password.py --sql --username admin
```

Tempel output `UPDATE`/`INSERT` di SQL editor (SQLite lokal atau Neon Console). Detail di [Membuat / Mengubah User Manual](#membuat--mengubah-user-manual).

### 4. Run

```bash
python main.py
```

Buka `http://127.0.0.1:2424` di browser.

**Note:** Local development otomatis pakai SQLite. Tidak perlu setup database apapun.

### 5. Jalankan Test & Lint

```bash
pip install -r requirements-dev.txt
ruff check .
pytest -q
```

## Setup (Production - Vercel + Neon)

### Prerequisites

1. Akun [Vercel](https://vercel.com/)
2. Akun [Neon](https://neon.tech/) (free tier tersedia)
3. Vercel CLI terinstall: `npm i -g vercel`
4. Google Service Account JSON key

### Step 1: Buat Database di Neon

1. Login ke [Neon Console](https://console.neon.tech/)
2. Buat project baru (atau pakai existing)
3. Copy **Connection String** dari dashboard:
   ```
   postgresql://username:password@ep-xxx.us-east-2.aws.neon.tech/dbname?sslmode=require
   ```

### Step 2: Convert Service Account ke Base64

Vercel tidak support file upload. Convert JSON key ke base64:

```bash
# Windows (PowerShell)
[Convert]::ToBase64String([IO.File]::ReadAllBytes("auth-xxx.json"))

# Linux/Mac
base64 -i auth-xxx.json
```

Copy hasilnya.

### Step 3: Setup Environment Variables di Vercel

```bash
vercel login
vercel link
```

Tambah environment variables:

```bash
vercel env add SPREADSHEET_NAME production
# Input: NGG Fun Walk Oct 2026 - Data Peserta (PAID)

vercel env add GOOGLE_CREDENTIALS_BASE64 production
# Input: (paste base64 string dari Step 2)

vercel env add DATABASE_URL production
# Input: (paste Neon connection string dari Step 1)
```

Buat akun admin pertama **manual** di Neon Console (SQL Editor):

1. Jalankan `python scripts/hash_password.py --sql --username admin` lokal
2. Tempel perintah `INSERT` hasilnya ke Neon SQL Editor → Execute

Setelah login pertama, buat akun staff tambahan dari menu **Backoffice → Users**.

### Step 4: Deploy

```bash
vercel --prod
```

### Step 5: Open di Browser

```
https://ngg-attendance.vercel.app/
```

## API Endpoints

Semua endpoint di bawah (kecuali `/`, `/health`, `/docs`, `POST /api/auth/login`) **membutuhkan cookie session** yang didapat dari login. Tanpa login → **401**; akses endpoint admin sebagai staff → **403**.

| Method | Endpoint | Akses | Description |
|--------|----------|-------|-------------|
| `GET` | `/` | - | Frontend (login → Race Desk UI) |
| `GET` | `/health` | - | Health check (`{"status": "ok", "database": "sqlite/neon", "participants": N}`; **503** jika DB error) |
| `GET` | `/docs` | - | Swagger UI (**local development saja**; **dimatikan di production**) |
| `POST` | `/api/auth/login` | - | Login `{username, password}` → set cookie `ngg_session` (HttpOnly); **401** salah password, **423** akun terkunci |
| `POST` | `/api/auth/logout` | sesi | Revoke session + clear cookie |
| `GET` | `/api/auth/me` | sesi | Profil user saat ini (`id`, `username`, `role`) |
| `GET` | `/api/registration/participant/{no_order}` | staff | Get participant by order number |
| `POST` | `/api/registration/check-in` | staff | Race pack pickup (+ audit, GSheets push async) |
| `POST` | `/api/registration/check-in/undo` | staff | **Batalkan** race pack pickup |
| `POST` | `/api/registration/attendance` | staff | Mark attendance (+ audit) |
| `POST` | `/api/registration/attendance/undo` | staff | **Batalkan** status hadir |
| `GET` | `/api/registration/participants` | staff | Get all participants |
| `GET` | `/api/registration/search?keyword=...` | staff | Search participants |
| `GET` | `/api/registration/stats` | staff | Get statistics |
| `GET` | `/api/admin/users` | admin | List akun |
| `POST` | `/api/admin/users` | admin | Buat akun `{username, password, role}` |
| `PATCH` | `/api/admin/users/{id}` | admin | Update password/role/is_active (tidak bisa nonaktifkan/demote diri sendiri) |
| `GET` | `/api/admin/audit` | admin | Log aktivitas (`limit`, `offset`, `action`, `actor`, `entity_id`) |
| `GET` | `/api/admin/stats` | admin | Statistik users/logs + top actor hari ini |

### Login & Sesi

```json
POST /api/auth/login
{ "username": "admin", "password": "<password-anda-min-8-karakter>" }
→ 200 { "status": "success", "user": { "id": 1, "username": "admin", "role": "admin", "is_active": true } }
Cookie: ngg_session=...; HttpOnly; SameSite=Lax; Secure (saat VERCEL=1)
```

- Password di-hash dengan **hashlib.scrypt** (stdlib, tanpa dependency tambahan), **minimal 8 karakter**
- 5× gagal login berturut-turut → akun terkunci 15 menit (HTTP **423**)
- Rate limit per-IP: default 30 percobaan login per 60 detik → HTTP **429**
- IP client diambil dari header `X-Forwarded-For` (akurat di belakang proxy Vercel)
- Unknown user tetal menjalankan dummy password verify (mitigasi user-enumeration timing)
- Session TTL default 12 jam (`SESSION_TTL_HOURS`)
- Role: `admin` (user + backoffice) / `staff` (operasional race desk)

### Membuat / Mengubah User Manual

Tidak ada auto-seed user. Buat atau ganti password lewat hash + SQL:

```bash
# 1. Generate hash (password diminta interaktif, echo tampil)
python scripts/hash_password.py

# 2. Atau langsung output SQL siap tempel (SQLite lokal / Neon Console)
python scripts/hash_password.py --sql --username admin

# 3. Verifikasi password cocok dengan hash tertentu
python scripts/hash_password.py --verify 'password-anda' 'scrypt$...'
```

Karena password di-hash dengan salt acak, **plaintext password tidak disimpan di mana pun** — satu-satunya cara mengubah password adalah menulis hash baru ke kolom `users.password_hash` (via script di atas, atau lewat menu Backoffice → Users setelah berhasil login).

### Request Body (Registration)

**Check-in:**
```json
POST /api/registration/check-in
{
  "no_order": "383"
}
```

**Attendance:**
```json
POST /api/registration/attendance
{
  "no_order": "383"
}
```

**Undo check-in / undo hadir** (body sama seperti di atas):
```json
POST /api/registration/check-in/undo
{ "no_order": "383" }

POST /api/registration/attendance/undo
{ "no_order": "383" }
```

## Project Structure

```
NGG-Attendance/
├── main.py                 # Local dev entry (create_app serve_static + docs on)
├── requirements.txt        # Python dependencies
├── requirements-dev.txt    # Dev: pytest, httpx, ruff
├── ruff.toml               # Lint config
├── vercel.json             # Vercel deployment config
├── .env.example            # Env template (copy ke .env)
├── .env                    # Environment variables (not committed)
├── .github/workflows/ci.yml# CI: ruff + pytest
├── auth-*.json             # Google service account key (not committed)
├── core/
│   ├── app.py              # Shared create_app (lifespan, handlers, /health)
│   ├── config.py           # Settings + startup validation
│   ├── db.py               # DB facade (pilih neon_db / sqlite_db)
│   ├── auth.py             # Password scrypt, session cookie, require_staff/admin
│   ├── ratelimit.py        # Sliding-window rate limiter (login per-IP)
│   ├── database.py         # Google Sheets connection + push helper (retry 3×)
│   ├── sqlite_db.py        # SQLite operations (local dev) + users/sessions/audit
│   └── neon_db.py          # Neon PostgreSQL operations (production) + users/sessions/audit
├── modules/
│   ├── auth/
│   │   ├── router.py       # login / logout / me (rate limit + dummy verify)
│   │   └── schemas.py      # LoginRequest
│   ├── admin/
│   │   ├── router.py       # users CRUD, audit list, admin stats
│   │   └── schemas.py      # CreateUserRequest, UpdateUserRequest (password min 8)
│   └── registration/
│       ├── router.py       # API routes (require_staff)
│       ├── schemas.py      # Pydantic models
│       └── services.py     # Business logic (write + audit + GSheets push)
├── tests/
│   ├── conftest.py         # Test fixtures (temp SQLite per test)
│   └── test_api.py         # Auth, RBAC, check-in/undo, rate limit, docs
├── data/
│   └── attendance.db       # SQLite database (auto-created, local only)
├── scripts/
│   └── hash_password.py    # Generate hash scrypt untuk buat/edit user manual via SQL
├── public/                 # Static files — satu-satunya sumber frontend
│   ├── index.html          # Login screen + gate + tabs (Input, List, Backoffice)
│   ├── styles.css
│   └── app.js              # Auth gate, fetchJson 401/403, backoffice UI
└── api/
    └── index.py            # Vercel serverless entry (docs disabled)
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SPREADSHEET_NAME` | Yes | Nama Google Spreadsheet |
| `CREDENTIALS_FILE` | Local only | Path ke file JSON Google Service Account |
| `DATABASE_URL` | Production | Neon PostgreSQL connection string |
| `GOOGLE_CREDENTIALS_BASE64` | Production | Base64 encoded Google Service Account JSON |
| `SESSION_TTL_HOURS` | No (default `12`) | Masa berlaku session cookie |
| `SESSION_COOKIE_NAME` | No (default `ngg_session`) | Nama cookie session |
| `LOGIN_MAX_FAILURES` | No (default `5`) | Jumlah gagal login sebelum lockout |
| `LOGIN_LOCK_MINUTES` | No (default `15`) | Durasi lockout (menit) |
| `LOGIN_RATE_LIMIT` | No (default `30`) | Max percobaan login per IP dalam window |
| `LOGIN_RATE_WINDOW_SECONDS` | No (default `60`) | Window rate limit login (detik) |

Salin `.env.example` → `.env` lalu isi nilai sesuai environment.

## Troubleshooting

### Database Auto-Detect

Sistem otomatis detect database yang digunakan:
- **SQLite**: Jika `DATABASE_URL` tidak diset (local development)
- **Neon PostgreSQL**: Jika `DATABASE_URL` diset (production)

Cek di health check endpoint:
```
GET /health
→ {"status": "ok", "database": "neon"}
```

### Google Sheets Sync Gagal

1. Pastikan service account email sudah di-share ke Google Sheets
2. Pastikan nama spreadsheet benar di `SPREADSHEET_NAME`
3. Cek logs di Vercel dashboard
4. Response check-in/attendance menyertakan field `gsheets_sync`:
   - `"queued"` — local dev, push di BackgroundTasks
   - `"ok"` / `"failed"` — production (Vercel), push sinkron dengan retry 3×
   Data tetap tersimpan di database meskipun push gagal — cek log Vercel untuk hasil push.

### Neon PostgreSQL Connection Error

1. Pastikan `DATABASE_URL` benar dan mengandung `sslmode=require`
2. Pastikan IP Vercel sudah di-whitelist di Neon (opsional, Neon default allow all)
3. Cek apakah database sudah dibuat di Neon Console

### Testing & Linting

```bash
pip install -r requirements-dev.txt
ruff check .
pytest -q
```

CI (GitHub Actions) menjalankan `ruff` + `pytest` otomatis di setiap push/PR ke `main`.

### Cold Start Lambat

Pertama kali akses setelah idle akan lambat (~5-10 detik) karena:
1. Vercel perlu spin up serverless function
2. App perlu sync data dari Google Sheets ke database

Setelah itu, request berikutnya akan sangat cepat (~1ms).

## License

Private - Momaz Team Only
