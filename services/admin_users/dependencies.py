"""
FastAPI auth dependencies for admin_users (Arch-23, §6.1).

Reads the JWT from the `lead_engine_auth` httpOnly cookie, verifies it,
loads the AdminUser row through `AdminUserCRUD`, and returns the model.
"""

from __future__ import annotations

from typing import Iterable

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db

from .auth import AUTH_COOKIE_NAME, decode_jwt
from .crud import AdminUserCRUD
from .models import AdminUser


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
) -> AdminUser:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    try:
        payload = decode_jwt(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    user = await AdminUserCRUD.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user


def require_role(*allowed_roles: int):
    """Dependency factory — role ints per §6.1 (0=admin, 1=growth, ... 6=viewer)."""

    async def _checker(user: AdminUser = Depends(get_current_user)) -> AdminUser:
        if allowed_roles and user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return user

    return _checker


def require_any_authenticated() -> Iterable:
    """Sugar — equivalent to `Depends(get_current_user)`."""
    return Depends(get_current_user)
