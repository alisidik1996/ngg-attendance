from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from core.auth import (
    _expires_at_iso,
    _is_locked,
    clear_session_cookie,
    client_meta,
    dummy_verify,
    get_current_user,
    hash_token,
    new_session_token,
    public_user,
    set_session_cookie,
    verify_password,
)
from core.config import settings
from core.db import db
from core.ratelimit import login_rate_limiter
from modules.auth.schemas import LoginRequest

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/login")
def login(payload: LoginRequest, request: Request):
    meta = client_meta(request)
    ip_key = meta["ip"] or "unknown"
    if not login_rate_limiter.allow(
        ip_key, settings.LOGIN_RATE_LIMIT, settings.LOGIN_RATE_WINDOW_SECONDS
    ):
        raise HTTPException(
            status_code=429,
            detail="Terlalu banyak percobaan login. Coba lagi nanti.",
        )

    username = payload.username.strip()
    user = db.get_user_by_username(username)

    if user and _is_locked(user.get("locked_until")):
        db.insert_audit_log(
            None, username, "login_failed", "user", username,
            "locked", meta["ip"], meta["user_agent"],
        )
        raise HTTPException(
            status_code=423,
            detail=f"Akun terkunci sampai {user['locked_until']} karena terlalu banyak gagal login",
        )

    if not user:
        dummy_verify(payload.password)
        db.insert_audit_log(
            None, username, "login_failed", "user", username,
            "unknown_user", meta["ip"], meta["user_agent"],
        )
        raise HTTPException(status_code=401, detail="Username atau password salah")

    if not verify_password(payload.password, user["password_hash"]):
        result = db.record_login_failure(
            username,
            lock_minutes=settings.LOGIN_LOCK_MINUTES,
            max_failures=settings.LOGIN_MAX_FAILURES,
        )
        detail = "Username atau password salah"
        if result.get("locked_until"):
            detail = f"Akun terkunci sampai {result['locked_until']}"
        db.insert_audit_log(
            user.get("id"), username, "login_failed", "user", username,
            detail, meta["ip"], meta["user_agent"],
        )
        raise HTTPException(status_code=401, detail=detail)

    if not int(user.get("is_active") or 0):
        db.insert_audit_log(
            user["id"], username, "login_failed", "user", username,
            "inactive", meta["ip"], meta["user_agent"],
        )
        raise HTTPException(status_code=403, detail="Akun tidak aktif")

    db.clear_login_failures(user["id"])
    token = new_session_token()
    db.create_session(
        user["id"], hash_token(token), _expires_at_iso(),
        meta["ip"], meta["user_agent"],
    )
    db.insert_audit_log(
        user["id"], username, "login", "user", username,
        "", meta["ip"], meta["user_agent"],
    )

    resp = JSONResponse(content={
        "status": "success",
        "user": public_user(user),
    })
    set_session_cookie(resp, token)
    return resp


@router.post("/logout")
def logout(request: Request):
    meta = client_meta(request)
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if token:
        session = db.get_session_by_token_hash(hash_token(token))
        if session:
            db.revoke_session(hash_token(token))
            db.insert_audit_log(
                session.get("user_id"), "", "logout", "session", "",
                "", meta["ip"], meta["user_agent"],
            )
    resp = JSONResponse(content={"status": "success"})
    clear_session_cookie(resp)
    return resp


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return {"status": "success", "user": public_user(user)}
