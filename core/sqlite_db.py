import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.environ.get("NGG_SQLITE_PATH") or os.path.join(BASE_DIR, "data", "attendance.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'staff',
    is_active INTEGER NOT NULL DEFAULT 1,
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    ip TEXT DEFAULT '',
    user_agent TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor_id INTEGER,
    actor_username TEXT DEFAULT '',
    action TEXT NOT NULL,
    entity TEXT DEFAULT '',
    entity_id TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    ip TEXT DEFAULT '',
    user_agent TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_ts ON audit_logs(ts);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
"""

KNOWN_COLUMNS = [
    "order_number", "nama_lengkap_ibu", "nama_lengkap_ayah", "nama_anak", "usia_bayi",
    "item_name", "paket", "uk_kaos_ibu", "uk_kaos_ayah", "order_status",
    "nomor_wa", "email", "status_diambil", "waktu_diambil",
    "status_hadir", "waktu_hadir"
]

STATUS_COLUMNS = ["status_diambil", "waktu_diambil", "status_hadir", "waktu_hadir"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _escape_like(value: str) -> str:
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> bool:
    """Create schema. Returns True if nama_lengkap_ayah was just added (needs backfill)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    try:
        conn.executescript(SCHEMA)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(participants)").fetchall()]
        migrated = "nama_lengkap_ayah" not in cols
        if migrated:
            conn.execute("ALTER TABLE participants ADD COLUMN nama_lengkap_ayah TEXT DEFAULT ''")
            logger.info("SQLite migration: added nama_lengkap_ayah column.")
        conn.commit()
        logger.info("SQLite database initialized.")
        return migrated
    finally:
        conn.close()


def count_participants() -> int:
    conn = get_db()
    try:
        row = conn.execute("SELECT COUNT(*) FROM participants").fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def _insert_audit(conn, actor_id, actor_username, action, entity, entity_id, detail, ip, user_agent):
    conn.execute(
        """INSERT INTO audit_logs (ts, actor_id, actor_username, action, entity, entity_id, detail, ip, user_agent)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (_now_iso(), actor_id, actor_username or "", action, entity or "", entity_id or "",
         detail or "", ip or "", user_agent or ""),
    )


def insert_audit_log(actor_id, actor_username, action, entity="", entity_id="", detail="", ip="", user_agent=""):
    conn = get_db()
    try:
        _insert_audit(conn, actor_id, actor_username, action, entity, entity_id, detail, ip, user_agent)
        conn.commit()
    finally:
        conn.close()


def sync_from_gsheets():
    from core.database import gsheetConnection

    logger.info("Syncing data from Google Sheets to SQLite (merge)...")
    sheet = gsheetConnection()
    data = sheet.get_all_records()
    if not data:
        logger.warning("Google Sheets returned 0 records, skipping sync.")
        return

    conn = get_db()
    try:
        existing = {
            r["order_number"]: dict(r)
            for r in conn.execute(
                "SELECT order_number, status_diambil, waktu_diambil, status_hadir, waktu_hadir FROM participants"
            ).fetchall()
        }
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

            prev = existing.get(order_number)
            if prev:
                for sc in STATUS_COLUMNS:
                    if not str(vals[unique_cols.index(sc)] if sc in unique_cols else "").strip():
                        if str(prev.get(sc) or "").strip():
                            if sc not in unique_cols:
                                unique_cols.append(sc)
                                unique_vals.append(prev[sc])
                            else:
                                unique_vals[unique_cols.index(sc)] = prev[sc]

            placeholders = ", ".join(["?"] * len(unique_cols))
            col_names = ", ".join(unique_cols)
            updates = [f"{c} = excluded.{c}" for c in unique_cols if c != "order_number"]
            if updates:
                conflict_clause = (
                    f"ON CONFLICT(order_number) DO UPDATE SET {', '.join(updates)}"
                )
            else:
                conflict_clause = "ON CONFLICT(order_number) DO NOTHING"
            conn.execute(
                f"INSERT INTO participants ({col_names}) VALUES ({placeholders}) {conflict_clause}",
                unique_vals
            )

        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM participants").fetchone()[0]
        if skipped:
            logger.warning(f"Skipped {skipped} sheet row(s) with empty order_number.")
        logger.info(f"Sync complete: {count} participants in SQLite.")
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


def update_checkin(no_order: str, waktu: str, actor_id=None, actor_username="", ip="", user_agent="") -> bool:
    conn = get_db()
    try:
        cur = conn.execute(
            """UPDATE participants SET status_diambil = 'Sudah', waktu_diambil = ?
               WHERE order_number = ?
                 AND LOWER(COALESCE(TRIM(status_diambil), '')) != 'sudah'""",
            (waktu, no_order.strip())
        )
        updated = cur.rowcount > 0
        if updated:
            _insert_audit(conn, actor_id, actor_username, "check_in", "participant",
                          no_order.strip(), f"waktu={waktu}", ip, user_agent)
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_attendance(no_order: str, waktu: str, actor_id=None, actor_username="", ip="", user_agent="") -> bool:
    conn = get_db()
    try:
        cur = conn.execute(
            """UPDATE participants SET status_hadir = 'Hadir', waktu_hadir = ?
               WHERE order_number = ?
                 AND LOWER(COALESCE(TRIM(status_hadir), '')) != 'hadir'""",
            (waktu, no_order.strip())
        )
        updated = cur.rowcount > 0
        if updated:
            _insert_audit(conn, actor_id, actor_username, "attendance", "participant",
                          no_order.strip(), f"waktu={waktu}", ip, user_agent)
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def clear_checkin(no_order: str, actor_id=None, actor_username="", ip="", user_agent="") -> bool:
    conn = get_db()
    try:
        cur = conn.execute(
            """UPDATE participants SET status_diambil = '', waktu_diambil = ''
               WHERE order_number = ?
                 AND LOWER(COALESCE(TRIM(status_diambil), '')) = 'sudah'""",
            (no_order.strip(),)
        )
        cleared = cur.rowcount > 0
        if cleared:
            _insert_audit(conn, actor_id, actor_username, "undo_check_in", "participant",
                          no_order.strip(), "", ip, user_agent)
        conn.commit()
        return cleared
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def clear_attendance(no_order: str, actor_id=None, actor_username="", ip="", user_agent="") -> bool:
    conn = get_db()
    try:
        cur = conn.execute(
            """UPDATE participants SET status_hadir = '', waktu_hadir = ''
               WHERE order_number = ?
                 AND LOWER(COALESCE(TRIM(status_hadir), '')) = 'hadir'""",
            (no_order.strip(),)
        )
        cleared = cur.rowcount > 0
        if cleared:
            _insert_audit(conn, actor_id, actor_username, "undo_attendance", "participant",
                          no_order.strip(), "", ip, user_agent)
        conn.commit()
        return cleared
    except Exception:
        conn.rollback()
        raise
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


# --- Users ---

def count_users() -> int:
    conn = get_db()
    try:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def get_user_by_username(username: str):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username.strip(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_users():
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, username, role, is_active, failed_login_count, locked_until,
                      created_at, updated_at
               FROM users ORDER BY id"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_user(username: str, password_hash: str, role: str,
                actor_id=None, actor_username="", ip="", user_agent="") -> dict:
    now = _now_iso()
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO users (username, password_hash, role, is_active, failed_login_count,
                                  locked_until, created_at, updated_at)
               VALUES (?, ?, ?, 1, 0, NULL, ?, ?)""",
            (username.strip(), password_hash, role, now, now)
        )
        user_id = cur.lastrowid
        _insert_audit(conn, actor_id, actor_username, "user_create", "user",
                      username.strip(), f"role={role}", ip, user_agent)
        conn.commit()
        return {"id": user_id, "username": username.strip(), "role": role, "is_active": 1}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_user(user_id: int, password_hash=None, role=None, is_active=None,
                actor_id=None, actor_username="", ip="", user_agent="") -> bool:
    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return False
        user = dict(user)
        sets = []
        vals = []
        changes = []
        if password_hash is not None:
            sets.append("password_hash = ?")
            vals.append(password_hash)
            changes.append("password_reset")
        if role is not None and role != user["role"]:
            sets.append("role = ?")
            vals.append(role)
            changes.append(f"role={user['role']}->{role}")
        if is_active is not None and int(is_active) != int(user["is_active"]):
            sets.append("is_active = ?")
            vals.append(1 if is_active else 0)
            changes.append(f"active={bool(user['is_active'])}->{bool(is_active)}")
            if not is_active:
                sets.append("locked_until = NULL")
        if not sets:
            return False
        sets.append("updated_at = ?")
        vals.append(_now_iso())
        vals.append(user_id)
        conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", vals)
        _insert_audit(conn, actor_id, actor_username, "user_update", "user",
                      user["username"], "; ".join(changes), ip, user_agent)
        if password_hash is not None or is_active is False:
            conn.execute(
                "UPDATE sessions SET revoked = 1 WHERE user_id = ?",
                (user_id,)
            )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def record_login_failure(username: str, lock_minutes: int = 15, max_failures: int = 5) -> dict:
    conn = get_db()
    try:
        pending_lock = (datetime.now(timezone.utc) + timedelta(minutes=lock_minutes)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        cur = conn.execute(
            """UPDATE users
               SET failed_login_count = failed_login_count + 1,
                   locked_until = CASE
                       WHEN failed_login_count + 1 >= ? THEN ?
                       ELSE locked_until
                   END,
                   updated_at = ?
               WHERE username = ?""",
            (max_failures, pending_lock, _now_iso(), username.strip()),
        )
        if cur.rowcount == 0:
            conn.commit()
            return {"exists": False}
        row = conn.execute(
            "SELECT id, failed_login_count, locked_until FROM users WHERE username = ?",
            (username.strip(),)
        ).fetchone()
        conn.commit()
        return {
            "exists": True,
            "failed_login_count": row["failed_login_count"],
            "locked_until": row["locked_until"],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def clear_login_failures(user_id: int):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE users SET failed_login_count = 0, locked_until = NULL, updated_at = ? WHERE id = ?",
            (_now_iso(), user_id)
        )
        conn.commit()
    finally:
        conn.close()


# --- Sessions ---

def create_session(user_id: int, token_hash: str, expires_at: str, ip="", user_agent=""):
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO sessions (user_id, token_hash, created_at, expires_at, revoked, ip, user_agent)
               VALUES (?, ?, ?, ?, 0, ?, ?)""",
            (user_id, token_hash, _now_iso(), expires_at, ip or "", user_agent or "")
        )
        conn.commit()
    finally:
        conn.close()


def get_session_by_token_hash(token_hash: str):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE token_hash = ?",
            (token_hash,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def revoke_session(token_hash: str):
    conn = get_db()
    try:
        conn.execute("UPDATE sessions SET revoked = 1 WHERE token_hash = ?", (token_hash,))
        conn.commit()
    finally:
        conn.close()


def revoke_user_sessions(user_id: int):
    conn = get_db()
    try:
        conn.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


# --- Audit query ---

def list_audit_logs(limit: int = 50, offset: int = 0, action: str = None,
                    actor: str = None, entity_id: str = None):
    conn = get_db()
    try:
        clauses = []
        params = []
        if action:
            clauses.append("action = ?")
            params.append(action)
        if actor:
            clauses.append("LOWER(actor_username) LIKE ?")
            params.append(f"%{actor.strip().lower()}%")
        if entity_id:
            clauses.append("entity_id LIKE ?")
            params.append(f"%{entity_id.strip()}%")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        total = conn.execute(f"SELECT COUNT(*) FROM audit_logs {where}", params).fetchone()[0]
        params.extend([limit, offset])
        rows = conn.execute(
            f"""SELECT * FROM audit_logs {where}
                ORDER BY id DESC LIMIT ? OFFSET ?""",
            params
        ).fetchall()
        return {"total": total, "items": [dict(r) for r in rows]}
    finally:
        conn.close()


def get_admin_stats():
    conn = get_db()
    try:
        users_total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        users_active = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1").fetchone()[0]
        logs_total = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        logs_today = conn.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE ts LIKE ?",
            (f"{today}%",)
        ).fetchone()[0]
        top_actors = [
            dict(r) for r in conn.execute(
                """SELECT actor_username, COUNT(*) as count
                   FROM audit_logs
                   WHERE action IN ('check_in', 'attendance') AND ts LIKE ?
                   GROUP BY actor_username
                   ORDER BY count DESC LIMIT 10""",
                (f"{today}%",)
            ).fetchall()
        ]
        return {
            "users_total": users_total,
            "users_active": users_active,
            "logs_total": logs_total,
            "logs_today": logs_today,
            "top_actors_today": top_actors,
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
