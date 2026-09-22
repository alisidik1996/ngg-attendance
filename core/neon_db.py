import psycopg2
import psycopg2.extras
import logging
from datetime import datetime, timezone, timedelta
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

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'staff',
    is_active SMALLINT NOT NULL DEFAULT 1,
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token_hash TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked SMALLINT NOT NULL DEFAULT 0,
    ip TEXT DEFAULT '',
    user_agent TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
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


def _insert_audit(cur, actor_id, actor_username, action, entity, entity_id, detail, ip, user_agent):
    cur.execute(
        """INSERT INTO audit_logs (ts, actor_id, actor_username, action, entity, entity_id, detail, ip, user_agent)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (_now_iso(), actor_id, actor_username or "", action, entity or "", entity_id or "",
         detail or "", ip or "", user_agent or ""),
    )


def insert_audit_log(actor_id, actor_username, action, entity="", entity_id="", detail="", ip="", user_agent=""):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            _insert_audit(cur, actor_id, actor_username, action, entity, entity_id, detail, ip, user_agent)
        conn.commit()
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


def update_checkin(no_order: str, waktu: str, actor_id=None, actor_username="", ip="", user_agent="") -> bool:
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
                _insert_audit(cur, actor_id, actor_username, "check_in", "participant",
                              no_order.strip(), f"waktu={waktu}", ip, user_agent)
        if updated:
            conn.commit()
        else:
            conn.rollback()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_attendance(no_order: str, waktu: str, actor_id=None, actor_username="", ip="", user_agent="") -> bool:
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
                _insert_audit(cur, actor_id, actor_username, "attendance", "participant",
                              no_order.strip(), f"waktu={waktu}", ip, user_agent)
        if updated:
            conn.commit()
        else:
            conn.rollback()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def clear_checkin(no_order: str, actor_id=None, actor_username="", ip="", user_agent="") -> bool:
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
                _insert_audit(cur, actor_id, actor_username, "undo_check_in", "participant",
                              no_order.strip(), "", ip, user_agent)
        if cleared:
            conn.commit()
        else:
            conn.rollback()
        return cleared
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def clear_attendance(no_order: str, actor_id=None, actor_username="", ip="", user_agent="") -> bool:
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
                _insert_audit(cur, actor_id, actor_username, "undo_attendance", "participant",
                              no_order.strip(), "", ip, user_agent)
        if cleared:
            conn.commit()
        else:
            conn.rollback()
        return cleared
    except Exception:
        conn.rollback()
        raise
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


# --- Users ---

def count_users() -> int:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            row = cur.fetchone()
            return row[0] if row else 0
    finally:
        conn.close()


def get_user_by_username(username: str):
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE username = %s", (username.strip(),))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int):
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def list_users():
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT id, username, role, is_active, failed_login_count, locked_until,
                          created_at, updated_at
                   FROM users ORDER BY id"""
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def create_user(username: str, password_hash: str, role: str,
                actor_id=None, actor_username="", ip="", user_agent="") -> dict:
    now = _now_iso()
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO users (username, password_hash, role, is_active, failed_login_count,
                                      locked_until, created_at, updated_at)
                   VALUES (%s, %s, %s, 1, 0, NULL, %s, %s) RETURNING id""",
                (username.strip(), password_hash, role, now, now)
            )
            user_id = cur.fetchone()[0]
            _insert_audit(cur, actor_id, actor_username, "user_create", "user",
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
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if not user:
                return False
            user = dict(user)
            sets = []
            vals = []
            changes = []
            if password_hash is not None:
                sets.append("password_hash = %s")
                vals.append(password_hash)
                changes.append("password_reset")
            if role is not None and role != user["role"]:
                sets.append("role = %s")
                vals.append(role)
                changes.append(f"role={user['role']}->{role}")
            if is_active is not None and int(is_active) != int(user["is_active"]):
                sets.append("is_active = %s")
                vals.append(1 if is_active else 0)
                changes.append(f"active={bool(user['is_active'])}->{bool(is_active)}")
                if not is_active:
                    sets.append("locked_until = NULL")
            if not sets:
                return False
            sets.append("updated_at = %s")
            vals.append(_now_iso())
            vals.append(user_id)
            cur.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = %s", vals)
            _insert_audit(cur, actor_id, actor_username, "user_update", "user",
                          user["username"], "; ".join(changes), ip, user_agent)
            if password_hash is not None or is_active is False:
                cur.execute("UPDATE sessions SET revoked = 1 WHERE user_id = %s", (user_id,))
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
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, failed_login_count FROM users WHERE username = %s",
                (username.strip(),)
            )
            row = cur.fetchone()
            if not row:
                return {"exists": False}
            count = (row["failed_login_count"] or 0) + 1
            locked_until = None
            if count >= max_failures:
                locked_until = (
                    datetime.now(timezone.utc) + timedelta(minutes=lock_minutes)
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
            cur.execute(
                "UPDATE users SET failed_login_count = %s, locked_until = %s, updated_at = %s WHERE id = %s",
                (count, locked_until, _now_iso(), row["id"])
            )
        conn.commit()
        return {"exists": True, "failed_login_count": count, "locked_until": locked_until}
    finally:
        conn.close()


def clear_login_failures(user_id: int):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET failed_login_count = 0, locked_until = NULL, updated_at = %s WHERE id = %s",
                (_now_iso(), user_id)
            )
        conn.commit()
    finally:
        conn.close()


# --- Sessions ---

def create_session(user_id: int, token_hash: str, expires_at: str, ip="", user_agent=""):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO sessions (user_id, token_hash, created_at, expires_at, revoked, ip, user_agent)
                   VALUES (%s, %s, %s, %s, 0, %s, %s)""",
                (user_id, token_hash, _now_iso(), expires_at, ip or "", user_agent or "")
            )
        conn.commit()
    finally:
        conn.close()


def get_session_by_token_hash(token_hash: str):
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM sessions WHERE token_hash = %s", (token_hash,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def revoke_session(token_hash: str):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE sessions SET revoked = 1 WHERE token_hash = %s", (token_hash,))
        conn.commit()
    finally:
        conn.close()


def revoke_user_sessions(user_id: int):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE sessions SET revoked = 1 WHERE user_id = %s", (user_id,))
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
            clauses.append("action = %s")
            params.append(action)
        if actor:
            clauses.append("LOWER(actor_username) LIKE %s")
            params.append(f"%{actor.strip().lower()}%")
        if entity_id:
            clauses.append("entity_id LIKE %s")
            params.append(f"%{entity_id.strip()}%")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM audit_logs {where}", params)
            total = cur.fetchone()[0]
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"SELECT * FROM audit_logs {where} ORDER BY id DESC LIMIT %s OFFSET %s",
                params + [limit, offset]
            )
            items = [dict(r) for r in cur.fetchall()]
        return {"total": total, "items": items}
    finally:
        conn.close()


def get_admin_stats():
    conn = get_db()
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT
                    (SELECT COUNT(*) FROM users) as users_total,
                    (SELECT COUNT(*) FROM users WHERE is_active = 1) as users_active,
                    (SELECT COUNT(*) FROM audit_logs) as logs_total,
                    (SELECT COUNT(*) FROM audit_logs WHERE ts LIKE %s) as logs_today""",
                (f"{today}%",)
            )
            row = dict(cur.fetchone())
            cur.execute(
                """SELECT actor_username, COUNT(*) as count
                   FROM audit_logs
                   WHERE action IN ('check_in', 'attendance') AND ts LIKE %s
                   GROUP BY actor_username
                   ORDER BY count DESC LIMIT 10""",
                (f"{today}%",)
            )
            row["top_actors_today"] = [dict(r) for r in cur.fetchall()]
        return row
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
