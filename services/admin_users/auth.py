"""
Auth helpers for admin_users (Schema doc Arch-23, §7.1, §6.1).

DB-agnostic per CLAUDE.md "Services / integrations" rules — these functions
take primitives or framework objects and never touch `AsyncSession`.

Token transport: JWT in an httpOnly + Secure + SameSite=Lax cookie. Never
localStorage. 2FA deferred (Ishank lock per Arch-23). Federated THH-JWT
login is §9.6 v2.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from fastapi import Response

AUTH_COOKIE_NAME = "lead_engine_auth"
_JWT_ALGORITHM = "HS256"


def _jwt_secret() -> str:
    return os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-change-me")


def _jwt_ttl_hours() -> int:
    return int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_HOURS", "24"))


def _cookie_secure() -> bool:
    return os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def encode_jwt(*, user_id: int, role: int) -> tuple[str, int]:
    """Return (token, max_age_seconds)."""
    ttl = _jwt_ttl_hours()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=ttl)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, _jwt_secret(), algorithm=_JWT_ALGORITHM)
    return token, ttl * 3600


def decode_jwt(token: str) -> dict[str, Any]:
    """Raise jwt.InvalidTokenError subclasses on failure."""
    return jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGORITHM])


def set_auth_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=max_age_seconds,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
    )
