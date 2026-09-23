from tests.conftest import login, seed_participant


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db_connected"] is True


def test_docs_enabled_local_disabled_vercel(client):
    assert client.get("/docs").status_code == 200
    from fastapi.testclient import TestClient as TC

    from api.index import app as vercel_app
    with TC(vercel_app) as vc:
        assert vc.get("/docs").status_code == 404
        assert vc.get("/openapi.json").status_code == 404


def test_login_success_and_me(client, admin_user):
    login(client, admin_user)
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "admin"
    assert me.json()["user"]["role"] == "admin"


def test_login_wrong_password(client, admin_user):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-pass"})
    assert resp.status_code == 401


def test_login_unknown_user(client):
    resp = client.post("/api/auth/login", json={"username": "nope", "password": "whatever1"})
    assert resp.status_code == 401


def test_login_lockout_after_max_failures(client, admin_user):
    for _ in range(5):
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-pass"})
        assert resp.status_code == 401
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin-pass-123"})
    assert resp.status_code == 423


def test_logout_revokes_session(client, admin_user):
    login(client, admin_user)
    assert client.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def test_rate_limit_login(client, settings_reset=None):
    for i in range(30):
        resp = client.post("/api/auth/login", json={"username": f"u{i}", "password": "x"})
        if resp.status_code == 429:
            break
    else:
        resp = client.post("/api/auth/login", json={"username": "u99", "password": "x"})
    assert resp.status_code == 429


def test_password_min_length_on_create(client, admin_user):
    login(client, admin_user)
    resp = client.post(
        "/api/admin/users",
        json={"username": "shorty", "password": "short", "role": "staff"},
    )
    assert resp.status_code == 422


def test_staff_cannot_access_admin(client, staff_user):
    login(client, staff_user)
    assert client.get("/api/admin/users").status_code == 403


def test_unauthenticated_rejected(client):
    assert client.get("/api/registration/participants").status_code == 401
    assert client.get("/api/admin/users").status_code == 401


def test_check_in_and_undo_flow(client, staff_user):
    order = seed_participant("ORD100")
    login(client, staff_user)

    resp = client.post("/api/registration/check-in", json={"no_order": order})
    assert resp.status_code == 200, resp.text

    resp = client.post("/api/registration/check-in", json={"no_order": order})
    assert resp.status_code == 400

    resp = client.post("/api/registration/check-in/undo", json={"no_order": order})
    assert resp.status_code == 200

    resp = client.post("/api/registration/check-in", json={"no_order": order})
    assert resp.status_code == 200


def test_attendance_and_undo_flow(client, staff_user):
    order = seed_participant("ORD200")
    login(client, staff_user)

    resp = client.post("/api/registration/attendance", json={"no_order": order})
    assert resp.status_code == 200, resp.text

    resp = client.post("/api/registration/attendance", json={"no_order": order})
    assert resp.status_code == 400

    resp = client.post("/api/registration/attendance/undo", json={"no_order": order})
    assert resp.status_code == 200


def test_search_participant(client, staff_user):
    order = seed_participant("ORD300")
    login(client, staff_user)
    resp = client.get("/api/registration/search", params={"keyword": order})
    assert resp.status_code == 200
    assert resp.json()["total_found"] >= 1


def test_admin_user_crud_and_audit(client, admin_user, staff_user):
    login(client, admin_user)

    resp = client.post(
        "/api/admin/users",
        json={"username": "newuser", "password": "newuser-pass", "role": "staff"},
    )
    assert resp.status_code == 200

    resp = client.get("/api/admin/users")
    usernames = [u["username"] for u in resp.json()["data"]]
    assert "newuser" in usernames

    users = client.get("/api/admin/users").json()["data"]
    target = next(u for u in users if u["username"] == "newuser")

    resp = client.patch(
        f"/api/admin/users/{target['id']}",
        json={"is_active": False},
    )
    assert resp.status_code == 200

    resp = client.post("/api/auth/login", json={"username": "newuser", "password": "newuser-pass"})
    assert resp.status_code == 403

    audit = client.get("/api/admin/audit")
    assert audit.status_code == 200
    actions = [i["action"] for i in audit.json()["items"]]
    assert "user_create" in actions


def test_cannot_self_deactivate(client, admin_user):
    login(client, admin_user)
    me = client.get("/api/auth/me").json()["user"]
    resp = client.patch(f"/api/admin/users/{me['id']}", json={"is_active": False})
    assert resp.status_code == 400


def test_client_meta_uses_x_forwarded_for(client, admin_user, monkeypatch):
    login(client, admin_user)
    seen = {}

    from core import auth as auth_mod
    original = auth_mod.client_meta

    def spy(request):
        meta = original(request)
        seen.update(meta)
        return meta

    monkeypatch.setattr("modules.auth.router.client_meta", spy)
    client.post(
        "/api/auth/logout",
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert seen.get("ip") == "203.0.113.9"
