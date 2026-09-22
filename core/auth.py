import hashlib
import hmac
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import Depends, HTTPException, Request

from core.config import settings

if settings.use_neon:
    from core import neon_db as db
else:
    from core import sqlite_db as db

SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN,
    )
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, hash_hex = stored.split("$", 2)
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN,
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def _expires_at_iso() -> str:
    delta = timedelta(hours=settings.SESSION_TTL_HOURS)
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_expired(expires_at: str) -> bool:
    try:
        exp = datetime.strptime(expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= exp
    except Exception:
        return True


def _is_locked(locked_until) -> bool:
    if not locked_until:
        return False
    try:
        lock = datetime.strptime(locked_until, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < lock
    except Exception:
        return False


def client_meta(request: Request) -> dict:
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    return {"ip": ip, "user_agent": ua}


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "is_active": bool(user.get("is_active")),
    }


def get_current_user(request: Request) -> dict:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Belum login")
    session = db.get_session_by_token_hash(hash_token(token))
    if not session or int(session.get("revoked") or 0):
        raise HTTPException(status_code=401, detail="Sesi berakhir, silakan login ulang")
    if _is_expired(session["expires_at"]):
        raise HTTPException(status_code=401, detail="Sesi berakhir, silakan login ulang")
    user = db.get_user_by_id(session["user_id"])
    if not user or not int(user.get("is_active") or 0):
        raise HTTPException(status_code=401, detail="Akun tidak aktif")
    return user


def require_staff(user: dict = Depends(get_current_user)) -> dict:
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Akses admin diperlukan")
    return user


def set_session_cookie(response, token: str) -> None:
    max_age = settings.SESSION_TTL_HOURS * 3600
    response.set_cookie(
        settings.SESSION_COOKIE_NAME,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.is_vercel,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
