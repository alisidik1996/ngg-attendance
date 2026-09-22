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
- Push balik ke Google Sheets dilakukan sinkron sebelum response (dijamin selesai di Vercel)

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

Buat file `.env` di root project:

```env
SPREADSHEET_NAME=NGG Fun Walk Oct 2026 - Data Peserta (PAID)
CREDENTIALS_FILE=auth-xxx.json
```

### 4. Run

```bash
python main.py
```

Buka `http://127.0.0.1:2424` di browser.

**Note:** Local development otomatis pakai SQLite. Tidak perlu setup database apapun.

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

### Step 4: Deploy

```bash
vercel --prod
```

### Step 5: Open di Browser

```
https://ngg-attendance.vercel.app/
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Frontend (Race Desk UI) |
| `GET` | `/health` | Health check (returns `{"status": "ok", "database": "sqlite/neon", "participants": N}`; **503** jika DB error) |
| `GET` | `/docs` | Swagger UI documentation (**local development saja**; tidak di-route di Vercel) |
| `GET` | `/api/registration/participant/{no_order}` | Get participant by order number |
| `POST` | `/api/registration/check-in` | Race pack pickup |
| `POST` | `/api/registration/attendance` | Mark attendance |
| `GET` | `/api/registration/participants` | Get all participants |
| `GET` | `/api/registration/search?keyword=...` | Search participants |
| `GET` | `/api/registration/stats` | Get statistics |

### Request Body

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

## Project Structure

```
NGG-Attendance/
├── main.py                 # FastAPI app (local dev)
├── requirements.txt        # Python dependencies
├── vercel.json             # Vercel deployment config
├── .env                    # Environment variables (not committed)
├── auth-*.json             # Google service account key (not committed)
├── core/
│   ├── config.py           # Settings loader (SQLite vs Neon auto-detect)
│   ├── database.py         # Google Sheets connection + shared push helper
│   ├── sqlite_db.py        # SQLite operations (local dev)
│   └── neon_db.py          # Neon PostgreSQL operations (production)
├── modules/
│   └── registration/
│       ├── router.py       # API routes
│       ├── schemas.py      # Pydantic models
│       └── services.py     # Business logic (auto-detect DB)
├── data/
│   └── attendance.db       # SQLite database (auto-created, local only)
├── public/                 # Static files — satu-satunya sumber frontend
│   ├── index.html
│   ├── styles.css
│   └── app.js
└── api/
    └── index.py            # Vercel serverless entry point
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SPREADSHEET_NAME` | Yes | Nama Google Spreadsheet |
| `CREDENTIALS_FILE` | Local only | Path ke file JSON Google Service Account |
| `DATABASE_URL` | Production | Neon PostgreSQL connection string |
| `GOOGLE_CREDENTIALS_BASE64` | Production | Base64 encoded Google Service Account JSON |

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
4. Response check-in/attendance menyertakan field `gsheets_sync` (`"ok"` / `"failed"`). Jika `failed`, data tetap tersimpan di database — push dapat diulang dengan sync manual atau re-check.

### Neon PostgreSQL Connection Error

1. Pastikan `DATABASE_URL` benar dan mengandung `sslmode=require`
2. Pastikan IP Vercel sudah di-whitelist di Neon (opsional, Neon default allow all)
3. Cek apakah database sudah dibuat di Neon Console

### Cold Start Lambat

Pertama kali akses setelah idle akan lambat (~5-10 detik) karena:
1. Vercel perlu spin up serverless function
2. App perlu sync data dari Google Sheets ke database

Setelah itu, request berikutnya akan sangat cepat (~1ms).

## License

Private - Momaz Team Only
