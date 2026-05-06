"""
Inbound service-token auth for the THH → LEADS push (proposed §9.6).

Mirrors HH-BE's X-Service-Token pattern, but reverse direction. The
shared secret env var is `THH_INCOMING_SERVICE_TOKEN` — distinct from
`THH_BACKEND_SERVICE_TOKEN` (which LEADS uses to call HH-BE outward).

Why a separate token:
- Compromise of one direction shouldn't pivot to the other.
- Easier rotation: roll one without redeploying both sides simultaneously.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, status


_TOKEN_HEADER = "X-Service-Token"


def _expected_token() -> str:
    return (os.getenv("THH_INCOMING_SERVICE_TOKEN") or "").strip()


async def require_service_token(
    x_service_token: str | None = Header(default=None, alias=_TOKEN_HEADER),
) -> None:
    """
    FastAPI dependency. Raises 401 if the inbound `X-Service-Token`
    header is missing or doesn't match `THH_INCOMING_SERVICE_TOKEN`.

    Uses `hmac.compare_digest` to avoid timing-attack leaks on the
    secret. Strips both sides so trailing newlines from copy-paste in
    Coolify don't surprise us.
    """
    expected = _expected_token()
    if not expected:
        # Server misconfiguration — fail closed in prod, fail closed
        # everywhere (no implicit "dev allows all") to avoid drift.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="THH_INCOMING_SERVICE_TOKEN not configured",
        )
    presented = (x_service_token or "").strip()
    if not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing service token",
        )
