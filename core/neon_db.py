import psycopg2
import psycopg2.extras
import logging
from core.config import settings

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS participants (
    id SERIAL PRIMARY KEY,
    order_number TEXT UNIQUE NOT NULL,
    nama_lengkap_ibu TEXT DEFAULT '',
    nama_anak TEXT DEFAULT '',
    usia_bayi TEXT DEFAULT '',
    item_name TEXT DEFAULT '',
    paket TEXT DEFAULT '',
    uk_kaos_ibu TEXT DEFAULT '',
    uk_kaos_ayah TEXT DEFAULT '',
    order_status TEXT DEFAULT '',
    nomor_wa TEXT DEFAULT '',
    email TEXT DEFAULT '',
    status_diambil TEXT DEFAULT '',
    waktu_diambil TEXT DEFAULT '',
    status_hadir TEXT DEFAULT '',
    waktu_hadir TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_order_number ON participants(order_number);
"""

KNOWN_COLUMNS = [
    "order_number", "nama_lengkap_ibu", "nama_anak", "usia_bayi",
    "item_name", "paket", "uk_kaos_ibu", "uk_kaos_ayah", "order_status",
    "nomor_wa", "email", "status_diambil", "waktu_diambil",
    "status_hadir", "waktu_hadir"
]


def _normalize_dsn(dsn: str) -> str:
    dsn = dsn.strip()
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    if "sslmode=" not in dsn:
        sep = "&" if "?" in dsn else "?"
        dsn = f"{dsn}{sep}sslmode=require"
    return dsn


def get_db():
    conn = psycopg2.connect(_normalize_dsn(settings.DATABASE_URL))
    conn.autocommit = False
    return conn


def init_db():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
        conn.commit()
        logger.info("Neon PostgreSQL database initialized.")
    finally:
        conn.close()


def count_participants():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM participants")
            return cur.fetchone()[0]
    finally:
        conn.close()


def sync_from_gsheets():
    from core.database import gsheetConnection

    logger.info("Syncing data from Google Sheets to Neon PostgreSQL...")
    sheet = gsheetConnection()
    data = sheet.get_all_records()
    if not data:
        logger.warning("Google Sheets returned 0 records.")
        return

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM participants")
            for row in data:
                cols = []
                vals = []
                for key, val in row.items():
                    clean_key = key.strip()
                    if clean_key in KNOWN_COLUMNS:
                        cols.append(clean_key)
                        vals.append(str(val) if val is not None else "")

                cols.append("order_number")
                vals.append(str(row.get("order_number", "")))

                unique_cols = list(dict.fromkeys(cols))
                unique_vals = [vals[cols.index(c)] for c in unique_cols]

                placeholders = ", ".join(["%s"] * len(unique_cols))
                col_names = ", ".join(unique_cols)
                cur.execute(
                    f"INSERT INTO participants ({col_names}) VALUES ({placeholders}) ON CONFLICT (order_number) DO UPDATE SET {', '.join(f'{c} = EXCLUDED.{c}' for c in unique_cols if c != 'order_number')}",
                    unique_vals
                )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM participants")
            count = cur.fetchone()[0]
        logger.info(f"Sync complete: {count} participants loaded to Neon PostgreSQL.")
    finally:
        conn.close()


def get_participant_by_order(no_order: str):
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM participants WHERE order_number = %s", (no_order.strip(),))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def update_checkin(no_order: str, waktu: str):
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT status_diambil FROM participants WHERE order_number = %s", (no_order.strip(),))
            row = cur.fetchone()

            if row and str(row["status_diambil"] or "").strip().lower() == "sudah":
                conn.rollback()
                return False

            cur.execute(
                "UPDATE participants SET status_diambil = 'Sudah', waktu_diambil = %s WHERE order_number = %s",
                (waktu, no_order.strip())
            )
        conn.commit()
        return True
    finally:
        conn.close()


def update_attendance(no_order: str, waktu: str):
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT status_hadir FROM participants WHERE order_number = %s", (no_order.strip(),))
            row = cur.fetchone()

            if row and str(row["status_hadir"] or "").strip().lower() == "hadir":
                conn.rollback()
                return False

            cur.execute(
                "UPDATE participants SET status_hadir = 'Hadir', waktu_hadir = %s WHERE order_number = %s",
                (waktu, no_order.strip())
            )
        conn.commit()
        return True
    finally:
        conn.close()


def get_all_participants():
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM participants ORDER BY id")
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()


def search_participants(keyword: str):
    conn = get_db()
    try:
        like = f"%{keyword.strip().lower()}%"
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT * FROM participants
                   WHERE LOWER(order_number) LIKE %s
                      OR LOWER(nomor_wa) LIKE %s
                      OR LOWER(email) LIKE %s""",
                (like, like, like)
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()


def get_statistics():
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    COALESCE(SUM(CASE WHEN LOWER(status_diambil) = 'sudah' THEN 1 ELSE 0 END), 0) as sudah_ambil,
                    COALESCE(SUM(CASE WHEN LOWER(status_hadir) = 'hadir' THEN 1 ELSE 0 END), 0) as sudah_hadir
                FROM participants
            """)
            row = cur.fetchone()
            return {
                "total_peserta": row["total"],
                "race_pack_diambil": row["sudah_ambil"],
                "race_pack_belum": row["total"] - row["sudah_ambil"],
                "hadir_hari_h": row["sudah_hadir"]
            }
    finally:
        conn.close()


def push_checkin_to_gsheets(no_order: str):
    try:
        from core.database import gsheetConnection
        sheet = gsheetConnection()
        data = sheet.get_all_records()

        for idx, row in enumerate(data, start=2):
            if str(row.get("order_number", "")).strip() == no_order.strip():
                headers = sheet.row_values(1)
                status_col = headers.index("status_diambil") + 1
                waktu_col = headers.index("waktu_diambil") + 1

                participant = get_participant_by_order(no_order)
                sheet.update_cells([
                    [idx, status_col, participant["status_diambil"]],
                    [idx, waktu_col, participant["waktu_diambil"]]
                ])
                logger.info(f"Pushed check-in for {no_order} to Google Sheets.")
                return
        logger.warning(f"Order {no_order} not found in Google Sheets.")
    except Exception as e:
        logger.error(f"Failed to push check-in to Google Sheets: {e}")


def push_attendance_to_gsheets(no_order: str):
    try:
        from core.database import gsheetConnection
        sheet = gsheetConnection()
        data = sheet.get_all_records()

        for idx, row in enumerate(data, start=2):
            if str(row.get("order_number", "")).strip() == no_order.strip():
                headers = sheet.row_values(1)
                status_col = headers.index("status_hadir") + 1
                waktu_col = headers.index("waktu_hadir") + 1

                participant = get_participant_by_order(no_order)
                sheet.update_cells([
                    [idx, status_col, participant["status_hadir"]],
                    [idx, waktu_col, participant["waktu_hadir"]]
                ])
                logger.info(f"Pushed attendance for {no_order} to Google Sheets.")
                return
        logger.warning(f"Order {no_order} not found in Google Sheets.")
    except Exception as e:
        logger.error(f"Failed to push attendance to Google Sheets: {e}")
