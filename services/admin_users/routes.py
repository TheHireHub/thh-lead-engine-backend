"""FastAPI routes for admin_users (Schema doc §7.1, §6.1, Arch-23)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.audit.crud import AuditLogCRUD
from services.common.envelope import ok

from .auth import (
    clear_auth_cookie,
    encode_jwt,
    hash_password,
    set_auth_cookie,
    verify_password,
)
from .crud import AdminUserCRUD
from .dependencies import get_current_user, require_role
from .enums import ADMIN_ROLES, get_label
from .models import AdminUser
from .schemas import AdminUserCreate, AdminUserOut, AdminUserUpdate, LoginRequest

router = APIRouter(prefix="/api/admin-users", tags=["admin_users"])


def _serialize(user: AdminUser) -> dict:
    out = AdminUserOut.model_validate(user).model_dump(mode="json")
    out["role_label"] = get_label(ADMIN_ROLES, user.role)
    return out


# ---------------------------------------------------------------------------
# Auth (Arch-23) — JWT in httpOnly + Secure + SameSite=Lax cookie
# ---------------------------------------------------------------------------
@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await AdminUserCRUD.get_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid email or password"
        )

    token, max_age = encode_jwt(user_id=user.id, role=user.role)
    set_auth_cookie(response, token, max_age)

    await AdminUserCRUD.update_last_login(db, user)
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="admin_user",
        entity_id=user.id,
        action="login",
        ip_address=request.client.host if request.client else None,
    )

    return ok(_serialize(user), message="login successful")


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(get_current_user),
) -> dict:
    clear_auth_cookie(response)
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="admin_user",
        entity_id=user.id,
        action="logout",
        ip_address=request.client.host if request.client else None,
    )
    return ok(message="logged out")


@router.get("/me")
async def me(user: AdminUser = Depends(get_current_user)) -> dict:
    return ok(_serialize(user))


# ---------------------------------------------------------------------------
# Admin-only management — role 0 (admin) per §6.1
# ---------------------------------------------------------------------------
@router.get("/")
async def list_users(
    role: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_role(0)),
) -> dict:
    users = await AdminUserCRUD.list_all(db, role=role)
    return ok([_serialize(u) for u in users])


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_role(0)),
) -> dict:
    user = await AdminUserCRUD.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="admin user not found")
    return ok(_serialize(user))


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: AdminUserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role(0)),
) -> dict:
    if await AdminUserCRUD.get_by_email(db, payload.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already in use")

    user = await AdminUserCRUD.create(
        db,
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        role=payload.role,
    )
    await AuditLogCRUD.record(
        db,
        actor_user_id=actor.id,
        entity_type="admin_user",
        entity_id=user.id,
        action="create",
        after_json={"email": user.email, "role": user.role},
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(user), message="admin user created")


@router.patch("/{user_id}")
async def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role(0)),
) -> dict:
    user = await AdminUserCRUD.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="admin user not found")
    before = {"first_name": user.first_name, "last_name": user.last_name, "role": user.role}
    user = await AdminUserCRUD.update(db, user, **payload.model_dump(exclude_unset=True))
    await AuditLogCRUD.record(
        db,
        actor_user_id=actor.id,
        entity_type="admin_user",
        entity_id=user.id,
        action="update",
        before_json=before,
        after_json={"first_name": user.first_name, "last_name": user.last_name, "role": user.role},
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(user), message="admin user updated")


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_role(0)),
) -> dict:
    user = await AdminUserCRUD.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="admin user not found")
    await AdminUserCRUD.soft_delete(db, user)
    await AuditLogCRUD.record(
        db,
        actor_user_id=actor.id,
        entity_type="admin_user",
        entity_id=user.id,
        action="delete",
        ip_address=request.client.host if request.client else None,
    )
    return ok(message="admin user deleted")
