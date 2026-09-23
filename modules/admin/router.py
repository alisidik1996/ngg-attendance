from fastapi import APIRouter, Depends, HTTPException, Query, Request

from core.auth import (
    client_meta,
    hash_password,
    require_admin,
)
from core.db import db
from modules.admin.schemas import CreateUserRequest, UpdateUserRequest

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/users")
def list_users_endpoint(user: dict = Depends(require_admin)):
    return {"status": "success", "data": db.list_users()}


@router.post("/users")
def create_user_endpoint(payload: CreateUserRequest, request: Request,
                         actor: dict = Depends(require_admin)):
    role = payload.role if payload.role in ("admin", "staff") else "staff"
    username = payload.username.strip()
    if db.get_user_by_username(username):
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    meta = client_meta(request)
    created = db.create_user(
        username, hash_password(payload.password), role,
        actor_id=actor["id"], actor_username=actor["username"],
        ip=meta["ip"], user_agent=meta["user_agent"],
    )
    return {"status": "success", "user": created}


@router.patch("/users/{user_id}")
def update_user_endpoint(user_id: int, payload: UpdateUserRequest, request: Request,
                         actor: dict = Depends(require_admin)):
    if user_id == actor["id"] and payload.is_active is False:
        raise HTTPException(status_code=400, detail="Tidak dapat menonaktifkan akun sendiri")
    if user_id == actor["id"] and payload.role and payload.role != "admin":
        raise HTTPException(status_code=400, detail="Tidak dapat mengubah role akun sendiri")

    password_hash = hash_password(payload.password) if payload.password else None
    role = payload.role if payload.role in ("admin", "staff") else None
    meta = client_meta(request)
    updated = db.update_user(
        user_id,
        password_hash=password_hash,
        role=role,
        is_active=payload.is_active,
        actor_id=actor["id"], actor_username=actor["username"],
        ip=meta["ip"], user_agent=meta["user_agent"],
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return {"status": "success"}


@router.get("/audit")
def list_audit_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str = Query(default=None),
    actor: str = Query(default=None),
    entity_id: str = Query(default=None),
    user: dict = Depends(require_admin),
):
    result = db.list_audit_logs(
        limit=limit, offset=offset,
        action=action or None, actor=actor or None, entity_id=entity_id or None,
    )
    return {"status": "success", **result}


@router.get("/stats")
def admin_stats_endpoint(user: dict = Depends(require_admin)):
    participants = db.get_statistics()
    admin = db.get_admin_stats()
    return {
        "status": "success",
        "participants": participants,
        "admin": admin,
    }
