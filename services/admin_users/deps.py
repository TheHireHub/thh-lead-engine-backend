"""
FastAPI auth dependencies for admin_users (Arch-23, §6.1).

Reads the JWT from the `lead_engine_session` httpOnly cookie, verifies it,
loads the AdminUser row through `AdminUserCRUD`, and returns the model.
"""

from __future__ import annotations

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db

from .crud import AdminUserCRUD
from .jwt_utils import AUTH_COOKIE_NAME, decode_access_token
from .models import AdminUser


async def current_user(
    db: AsyncSession = Depends(get_db),
    token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
) -> AdminUser:
    """
    Resolve the authenticated admin user from the cookie. Raises 401 on any
    failure. Use as `Depends(current_user)` in route signatures.
    """
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    sub = payload.get("user_id") or payload.get("sub")
    try:
        user_id = int(sub) if sub is not None else None
    except (TypeError, ValueError):
        user_id = None
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    user = await AdminUserCRUD.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user


# Backwards-compatible alias — older code may import `get_current_user`.
get_current_user = current_user


def require_role(*allowed_roles: int):
    """Dependency factory — role ints per §6.1 (0=admin, 1=growth, ... 6=viewer)."""

    async def _checker(user: AdminUser = Depends(current_user)) -> AdminUser:
        if allowed_roles and user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return user

    return _checker
