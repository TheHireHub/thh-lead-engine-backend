"""
JWT + cookie helpers for admin auth (Schema doc Arch-23).

DB-agnostic per CLAUDE.md "Services / integrations" rules — no AsyncSession.

Token transport: JWT in an httpOnly + Secure + SameSite=Lax cookie named
`lead_engine_session` (frontend `src/middleware.ts` checks for this name).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from fastapi import Response

AUTH_COOKIE_NAME = "lead_engine_session"
_JWT_ALGORITHM = "HS256"


_DEV_JWT_DEFAULT = "dev-jwt-secret-change-me"


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY", _DEV_JWT_DEFAULT)
    if (os.getenv("APP_ENV", "development").lower() == "production") and (
        not secret or secret == _DEV_JWT_DEFAULT or "change-me" in secret.lower()
    ):
        raise RuntimeError(
            "JWT_SECRET_KEY must be set to a strong, non-default value in production"
        )
    return secret


def _jwt_ttl_hours() -> int:
    return int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_HOURS", "24"))


def _cookie_secure() -> bool:
    return os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"


def _cookie_domain() -> str | None:
    return os.getenv("SESSION_COOKIE_DOMAIN") or None


def _cookie_samesite() -> str:
    return os.getenv("SESSION_COOKIE_SAMESITE", "lax").lower()


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(*, user_id: int, role: int) -> tuple[str, int]:
    """Returns (token, max_age_seconds)."""
    ttl = _jwt_ttl_hours()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=ttl)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "user_id": user_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, _jwt_secret(), algorithm=_JWT_ALGORITHM)
    return token, ttl * 3600


def decode_access_token(token: str) -> dict[str, Any]:
    """Raise jwt.InvalidTokenError subclasses on failure."""
    return jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGORITHM])


def set_auth_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=max_age_seconds,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path="/",
        domain=_cookie_domain(),
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        domain=_cookie_domain(),
    )
