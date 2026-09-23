import os

os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("SPREADSHEET_NAME", "test-sheet")
os.environ.setdefault("CREDENTIALS_FILE", "missing.json")
os.environ.pop("VERCEL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core import sqlite_db  # noqa: E402
from core.auth import hash_password  # noqa: E402
from core.ratelimit import login_rate_limiter  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _test_env(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_db, "DB_PATH", str(tmp_path / "test.db"))
    login_rate_limiter.reset()
    sqlite_db.init_db()
    yield
    login_rate_limiter.reset()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_user(client):
    sqlite_db.create_user("admin", hash_password("admin-pass-123"), "admin")
    return {"username": "admin", "password": "admin-pass-123"}


@pytest.fixture()
def staff_user(client):
    sqlite_db.create_user("staff", hash_password("staff-pass-123"), "staff")
    return {"username": "staff", "password": "staff-pass-123"}


def login(client, user):
    resp = client.post("/api/auth/login", json=user)
    assert resp.status_code == 200, resp.text
    return resp


def seed_participant(order_number: str = "ORD001"):
    conn = sqlite_db.get_db()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO participants
               (order_number, nama_lengkap_ibu, nama_anak, nomor_wa, email)
               VALUES (?, ?, ?, ?, ?)""",
            (order_number, "Ibu Test", "Anak Test", "0812000000", "test@example.com"),
        )
        conn.commit()
    finally:
        conn.close()
    return order_number
