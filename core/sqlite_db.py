import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "attendance.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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


def _escape_like(value: str) -> str:
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        logger.info("SQLite database initialized.")
    finally:
        conn.close()


def count_participants() -> int:
    conn = get_db()
    try:
        row = conn.execute("SELECT COUNT(*) FROM participants").fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def sync_from_gsheets():
    from core.database import gsheetConnection

    logger.info("Syncing data from Google Sheets to SQLite...")
    sheet = gsheetConnection()
    data = sheet.get_all_records()
    if not data:
        logger.warning("Google Sheets returned 0 records, skipping sync.")
        return

    conn = get_db()
    try:
        conn.execute("DELETE FROM participants")
        skipped = 0
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

            placeholders = ", ".join(["?"] * len(unique_cols))
            col_names = ", ".join(unique_cols)
            conn.execute(
                f"INSERT OR REPLACE INTO participants ({col_names}) VALUES ({placeholders})",
                unique_vals
            )

        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM participants").fetchone()[0]
        if skipped:
            logger.warning(f"Skipped {skipped} sheet row(s) with empty order_number.")
        logger.info(f"Sync complete: {count} participants loaded to SQLite.")
    finally:
        conn.close()


def get_participant_by_order(no_order: str):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM participants WHERE order_number = ?",
            (no_order.strip(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_checkin(no_order: str, waktu: str) -> bool:
    conn = get_db()
    try:
        cur = conn.execute(
            """UPDATE participants SET status_diambil = 'Sudah', waktu_diambil = ?
               WHERE order_number = ?
                 AND LOWER(COALESCE(TRIM(status_diambil), '')) != 'sudah'""",
            (waktu, no_order.strip())
        )
        updated = cur.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


def update_attendance(no_order: str, waktu: str) -> bool:
    conn = get_db()
    try:
        cur = conn.execute(
            """UPDATE participants SET status_hadir = 'Hadir', waktu_hadir = ?
               WHERE order_number = ?
                 AND LOWER(COALESCE(TRIM(status_hadir), '')) != 'hadir'""",
            (waktu, no_order.strip())
        )
        updated = cur.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


def get_all_participants():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM participants ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_participants(keyword: str):
    conn = get_db()
    try:
        like = f"%{_escape_like(keyword.strip().lower())}%"
        rows = conn.execute(
            """SELECT * FROM participants
               WHERE LOWER(order_number) LIKE ? ESCAPE '!'
                  OR LOWER(nomor_wa) LIKE ? ESCAPE '!'
                  OR LOWER(email) LIKE ? ESCAPE '!'""",
            (like, like, like)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_statistics():
    conn = get_db()
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                COALESCE(SUM(CASE WHEN LOWER(status_diambil) = 'sudah' THEN 1 ELSE 0 END), 0) as sudah_ambil,
                COALESCE(SUM(CASE WHEN LOWER(status_hadir) = 'hadir' THEN 1 ELSE 0 END), 0) as sudah_hadir
            FROM participants
        """).fetchone()
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
