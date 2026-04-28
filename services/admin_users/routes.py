"""FastAPI routes for admin_users (Schema doc §7.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.common.envelope import ok

from .crud import AdminUserCRUD
from .enums import ADMIN_ROLES, get_label
from .schemas import AdminUserCreate, AdminUserOut, AdminUserUpdate

router = APIRouter(prefix="/api/admin-users", tags=["admin_users"])


def _serialize(user) -> dict:
    out = AdminUserOut.model_validate(user).model_dump()
    out["role_label"] = get_label(ADMIN_ROLES, user.role)
    return out


@router.get("/")
async def list_users(role: int | None = None, db: AsyncSession = Depends(get_db)) -> dict:
    users = await AdminUserCRUD.list_all(db, role=role)
    return ok([_serialize(u) for u in users])


@router.get("/{user_id}")
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    user = await AdminUserCRUD.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="admin user not found")
    return ok(_serialize(user))


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(payload: AdminUserCreate, db: AsyncSession = Depends(get_db)) -> dict:
    if await AdminUserCRUD.get_by_email(db, payload.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already in use")
    # Password hashing belongs in a future auth service; placeholder for stub.
    from passlib.hash import bcrypt

    user = await AdminUserCRUD.create(
        db,
        email=payload.email,
        password_hash=bcrypt.hash(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        role=payload.role,
    )
    return ok(_serialize(user), message="admin user created")


@router.patch("/{user_id}")
async def update_user(user_id: int, payload: AdminUserUpdate, db: AsyncSession = Depends(get_db)) -> dict:
    user = await AdminUserCRUD.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="admin user not found")
    user = await AdminUserCRUD.update(db, user, **payload.model_dump(exclude_unset=True))
    return ok(_serialize(user), message="admin user updated")


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    user = await AdminUserCRUD.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="admin user not found")
    await AdminUserCRUD.soft_delete(db, user)
    return ok(message="admin user deleted")
