"""
Inbound service-token auth for the THH → LEADS push (proposed §9.6).

Mirrors HH-BE's X-Service-Token pattern, but reverse direction. Two
per-environment secrets are accepted:

- `THH_INCOMING_SERVICE_TOKEN_STAGE` — sent by stage HH-BE
- `THH_INCOMING_SERVICE_TOKEN_PROD`  — sent by prod HH-BE

The legacy single-token env var (`THH_INCOMING_SERVICE_TOKEN`) is still
accepted during rollout; rows inserted under that path get tagged with
the env named in `THH_DEFAULT_INBOUND_ENV` (defaults to stage). Once the
per-env vars are deployed everywhere in Coolify, the legacy fallback can
be dropped.

Why per-env tokens (not just one):
- Stamp the inbound row with `environment` so the LEADS toggle filters
  stage vs prod data cleanly (Feature A).
- Compromise of one env's secret doesn't leak the other.
- Each env can be rotated independently.
"""

from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import Header, HTTPException, status

from services.common.environment import ENV_PROD, ENV_STAGE


_TOKEN_HEADER = "X-Service-Token"


def _legacy_token() -> str:
    return (os.getenv("THH_INCOMING_SERVICE_TOKEN") or "").strip()


def _stage_token() -> str:
    return (os.getenv("THH_INCOMING_SERVICE_TOKEN_STAGE") or "").strip()


def _prod_token() -> str:
    return (os.getenv("THH_INCOMING_SERVICE_TOKEN_PROD") or "").strip()


def _legacy_default_env() -> int:
    raw = (os.getenv("THH_DEFAULT_INBOUND_ENV") or "").strip().lower()
    return ENV_PROD if raw in ("1", "prod", "production") else ENV_STAGE


def _match_token(presented: str) -> Optional[int]:
    """Return the env tag for a recognised token, or None if no match.

    `hmac.compare_digest` runs in constant time on equal-length inputs;
    for differing lengths it short-circuits — fine here since the
    presented secret is attacker-supplied and we never reveal which
    candidate matched.
    """
    if not presented:
        return None
    stage = _stage_token()
    if stage and hmac.compare_digest(presented, stage):
        return ENV_STAGE
    prod = _prod_token()
    if prod and hmac.compare_digest(presented, prod):
        return ENV_PROD
    legacy = _legacy_token()
    if legacy and hmac.compare_digest(presented, legacy):
        return _legacy_default_env()
    return None


async def require_service_token_with_env(
    x_service_token: str | None = Header(default=None, alias=_TOKEN_HEADER),
) -> int:
    """
    FastAPI dependency. Validates the inbound `X-Service-Token` and
    returns the originating environment (`ENV_STAGE`=0 / `ENV_PROD`=1)
    so the route can stamp newly-inserted anchor rows.

    Raises:
      - 503 if NO token is configured server-side (fail closed; no
        implicit dev-mode bypass).
      - 401 if the header is missing or doesn't match a known token.
    """
    if not any((_stage_token(), _prod_token(), _legacy_token())):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="no inbound service tokens configured",
        )
    presented = (x_service_token or "").strip()
    env = _match_token(presented)
    if env is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing service token",
        )
    return env


async def require_service_token(
    x_service_token: str | None = Header(default=None, alias=_TOKEN_HEADER),
) -> None:
    """Legacy boolean-style dependency — pass/fail only, no env tag.

    Kept so existing routes that don't yet care about env continue to
    work. New routes should prefer `require_service_token_with_env`
    and stamp the returned env on inbound anchor rows."""
    await require_service_token_with_env(x_service_token)
