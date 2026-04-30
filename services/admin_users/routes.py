"""
FastAPI routes for admin_users (Schema doc §7.1, §6.1, Arch-23).

Two route groups exposed by one parent `router` so `app.py` registration
stays unchanged:
- `/api/auth/*`         (login, logout, me)
- `/api/admin-users/*`  (admin-only CRUD on users)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.audit.crud import AuditLogCRUD
from services.common.envelope import ok

from .crud import AdminUserCRUD
from .deps import current_user, require_admin, require_dashboard_read
from .enums import ADMIN_ROLES, get_label
from .jwt_utils import (
    clear_auth_cookie,
    create_access_token,
    hash_password,
    set_auth_cookie,
    verify_password,
)
from .models import AdminUser
from .schemas import (
    AdminUserCreate,
    AdminUserOut,
    AdminUserUpdate,
    LoginRequest,
    TeamMemberOut,
)

# Sub-routers (parent `router` stitched at the bottom of this file).
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/admin-users", tags=["admin_users"])


def _serialize(user: AdminUser) -> dict:
    out = AdminUserOut.model_validate(user).model_dump(mode="json")
    out["role_label"] = get_label(ADMIN_ROLES, user.role)
    return out


# ---------------------------------------------------------------------------
# /api/auth — login / logout / me  (Arch-23)
# ---------------------------------------------------------------------------
@auth_router.post("/login")
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

    token, max_age = create_access_token(user_id=user.id, role=user.role)
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
    return ok({"user": _serialize(user)}, message="login successful")


@auth_router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(current_user),
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


@auth_router.get("/me")
async def me(user: AdminUser = Depends(current_user)) -> dict:
    return ok({"user": _serialize(user)})


# ---------------------------------------------------------------------------
# /api/admin-users — admin-only management (role 0 per §6.1)
# ---------------------------------------------------------------------------
@users_router.get("/team")
async def list_team(
    role: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """
    Minimal team roster (id, name, role, avatar) for non-admin dashboard
    consumers — Sales per-rep cards, Mgmt Board team list (BUG-019). No
    email or last_login leaked. Caller (RBAC-isolated) and unauthenticated
    requests are denied via `require_dashboard_read`.
    """
    users = await AdminUserCRUD.list_all(db, role=role)
    out = []
    for u in users:
        member = TeamMemberOut.model_validate(u).model_dump(mode="json")
        member["role_label"] = get_label(ADMIN_ROLES, u.role)
        out.append(member)
    return ok(out)


@users_router.get("")
async def list_users(
    role: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> dict:
    users = await AdminUserCRUD.list_all(db, role=role)
    return ok([_serialize(u) for u in users])


@users_router.get("/{user_id}")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> dict:
    user = await AdminUserCRUD.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="admin user not found")
    return ok(_serialize(user))


@users_router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: AdminUserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_admin),
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
        daily_call_target=payload.daily_call_target,
        avatar_color=payload.avatar_color,
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


@users_router.patch("/{user_id}")
async def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_admin),
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


@users_router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: AdminUser = Depends(require_admin),
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


# ---------------------------------------------------------------------------
# Parent router — stitched after all routes are registered above so that
# `include_router`'s route snapshot captures everything. `app.py` imports
# this object as `admin_users_router`.
# ---------------------------------------------------------------------------
router = APIRouter()
router.include_router(auth_router)
router.include_router(users_router)
