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
    nama_lengkap_ayah TEXT DEFAULT '',
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
    "order_number", "nama_lengkap_ibu", "nama_lengkap_ayah", "nama_anak", "usia_bayi",
    "item_name", "paket", "uk_kaos_ibu", "uk_kaos_ayah", "order_status",
    "nomor_wa", "email", "status_diambil", "waktu_diambil",
    "status_hadir", "waktu_hadir"
]

STATUS_COLUMNS = ["status_diambil", "waktu_diambil", "status_hadir", "waktu_hadir"]


def _escape_like(value: str) -> str:
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


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


def init_db() -> bool:
    """Create schema. Returns True if nama_lengkap_ayah was just added (needs backfill)."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
            cur.execute(
                """SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'participants' AND column_name = 'nama_lengkap_ayah'"""
            )
            migrated = cur.fetchone() is None
            if migrated:
                cur.execute("ALTER TABLE participants ADD COLUMN nama_lengkap_ayah TEXT DEFAULT ''")
                logger.info("Neon migration: added nama_lengkap_ayah column.")
        conn.commit()
        logger.info("Neon PostgreSQL database initialized.")
        return migrated
    finally:
        conn.close()


def count_participants() -> int:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM participants")
            row = cur.fetchone()
            return row[0] if row else 0
    finally:
        conn.close()


def sync_from_gsheets():
    from core.database import gsheetConnection

    logger.info("Syncing data from Google Sheets to Neon PostgreSQL (merge)...")
    sheet = gsheetConnection()
    data = sheet.get_all_records()
    if not data:
        logger.warning("Google Sheets returned 0 records, skipping sync.")
        return

    conn = get_db()
    try:
        existing = {}
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT order_number, status_diambil, waktu_diambil, status_hadir, waktu_hadir
                   FROM participants"""
            )
            for r in cur.fetchall():
                existing[r["order_number"]] = dict(r)

        skipped = 0
        with conn.cursor() as cur:
            for row in data:
                order_number = str(row.get("order_number", "") or "").strip()
                if not order_number:
                    skipped += 1
                    continue

                cols = []
                vals = []
                for key, val in row.items():
                    clean_key = key.strip()
                    if clean_key in KNOWN_COLUMNS:
                        cols.append(clean_key)
                        vals.append(str(val) if val is not None else "")

                cols.append("order_number")
                vals.append(order_number)

                unique_cols = list(dict.fromkeys(cols))
                unique_vals = [vals[cols.index(c)] for c in unique_cols]

                prev = existing.get(order_number)
                if prev:
                    for sc in STATUS_COLUMNS:
                        sheet_val = vals[unique_cols.index(sc)] if sc in unique_cols else ""
                        if not str(sheet_val).strip() and str(prev.get(sc) or "").strip():
                            if sc not in unique_cols:
                                unique_cols.append(sc)
                                unique_vals.append(prev[sc])
                            else:
                                unique_vals[unique_cols.index(sc)] = prev[sc]

                placeholders = ", ".join(["%s"] * len(unique_cols))
                col_names = ", ".join(unique_cols)
                updates = [f"{c} = EXCLUDED.{c}" for c in unique_cols if c != "order_number"]
                if updates:
                    conflict_clause = (
                        f"ON CONFLICT (order_number) DO UPDATE SET {', '.join(updates)}"
                    )
                else:
                    conflict_clause = "ON CONFLICT (order_number) DO NOTHING"
                cur.execute(
                    f"INSERT INTO participants ({col_names}) VALUES ({placeholders}) {conflict_clause}",
                    unique_vals
                )
        conn.commit()
        if skipped:
            logger.warning(f"Skipped {skipped} sheet row(s) with empty order_number.")
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM participants")
            row = cur.fetchone()
            count = row[0] if row else 0
        logger.info(f"Sync complete: {count} participants in Neon PostgreSQL.")
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


def update_checkin(no_order: str, waktu: str) -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE participants SET status_diambil = 'Sudah', waktu_diambil = %s
                   WHERE order_number = %s
                     AND LOWER(COALESCE(TRIM(status_diambil), '')) != 'sudah'""",
                (waktu, no_order.strip())
            )
            updated = cur.rowcount > 0
        if updated:
            conn.commit()
        else:
            conn.rollback()
        return updated
    finally:
        conn.close()


def update_attendance(no_order: str, waktu: str) -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE participants SET status_hadir = 'Hadir', waktu_hadir = %s
                   WHERE order_number = %s
                     AND LOWER(COALESCE(TRIM(status_hadir), '')) != 'hadir'""",
                (waktu, no_order.strip())
            )
            updated = cur.rowcount > 0
        if updated:
            conn.commit()
        else:
            conn.rollback()
        return updated
    finally:
        conn.close()


def clear_checkin(no_order: str) -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE participants SET status_diambil = '', waktu_diambil = ''
                   WHERE order_number = %s
                     AND LOWER(COALESCE(TRIM(status_diambil), '')) = 'sudah'""",
                (no_order.strip(),)
            )
            cleared = cur.rowcount > 0
        if cleared:
            conn.commit()
        else:
            conn.rollback()
        return cleared
    finally:
        conn.close()


def clear_attendance(no_order: str) -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE participants SET status_hadir = '', waktu_hadir = ''
                   WHERE order_number = %s
                     AND LOWER(COALESCE(TRIM(status_hadir), '')) = 'hadir'""",
                (no_order.strip(),)
            )
            cleared = cur.rowcount > 0
        if cleared:
            conn.commit()
        else:
            conn.rollback()
        return cleared
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
        like = f"%{_escape_like(keyword.strip().lower())}%"
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT * FROM participants
                   WHERE LOWER(order_number) LIKE %s ESCAPE '!'
                      OR LOWER(nomor_wa) LIKE %s ESCAPE '!'
                      OR LOWER(email) LIKE %s ESCAPE '!'""",
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


def push_checkin_to_gsheets(no_order: str) -> bool:
    from core.database import push_status_to_gsheets
    participant = get_participant_by_order(no_order)
    if not participant:
        logger.error(f"Cannot push check-in: participant {no_order} not found in DB.")
        return False
    return push_status_to_gsheets(no_order, "status_diambil", "waktu_diambil", participant)


def push_attendance_to_gsheets(no_order: str) -> bool:
    from core.database import push_status_to_gsheets
    participant = get_participant_by_order(no_order)
    if not participant:
        logger.error(f"Cannot push attendance: participant {no_order} not found in DB.")
        return False
    return push_status_to_gsheets(no_order, "status_hadir", "waktu_hadir", participant)
