"""
Cross-platform JD + search-fields fetch from HH-BE (Feature B).

The CRM Jobs Board "View JD" button needs to pull the live JD + every
search filter the recruiter set on the HH-BE side. Data is NEVER cached
in LEADS DB — this is a pure passthrough.

A single LEADS-BE container can talk to BOTH stage HH-BE and prod HH-BE.
Which host we hit is dictated by the LEADS row's `environment` column
(0=stage, 1=prod). Each host has its own service token in Coolify so
compromise of one env's secret doesn't leak the other.

Env vars consumed:
    THH_BACKEND_STAGE_URL              — e.g. https://stage-api.thehirehub.ai
    THH_BACKEND_PROD_URL               — e.g. https://api.thehirehub.ai
    THH_BACKEND_SERVICE_TOKEN_STAGE    — bearer for stage HH-BE
    THH_BACKEND_SERVICE_TOKEN_PROD     — bearer for prod HH-BE
    THH_BACKEND_BASE_URL               — legacy fallback (single host)
    THH_BACKEND_SERVICE_TOKEN          — legacy fallback (single token)

The legacy single-var pair stays accepted during rollout so the existing
five §9 touch points keep working until both stage + prod LEADS Coolify
containers ship the new variables.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from services.common.environment import ENV_PROD, ENV_STAGE


logger = logging.getLogger(__name__)


# Network timeout: HH-BE's get_job_by_id does ~10 sequential SELECTs (skills,
# industries, locations, etc.) — under stage load they complete well under
# 5s, but allow headroom for cold-start.
_FETCH_TIMEOUT_SECONDS: float = 15.0


# Hardcoded host fallbacks. These match the canonical production / stage
# DNS so a missing env var in Coolify still routes correctly. Override via
# THH_BACKEND_STAGE_URL / THH_BACKEND_PROD_URL when running locally.
_DEFAULT_HOSTS: dict[int, str] = {
    ENV_STAGE: "https://stage-api.thehirehub.ai",
    ENV_PROD: "https://api.thehirehub.ai",
}


class ThhJdFetchError(RuntimeError):
    """Raised on any failure path so the route layer can map to HTTP."""

    def __init__(self, message: str, *, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


def _host_for_environment(environment: int) -> str:
    """Return the HH-BE base URL for the row's env, no trailing slash."""
    if environment == ENV_STAGE:
        override = os.getenv("THH_BACKEND_STAGE_URL")
    elif environment == ENV_PROD:
        override = os.getenv("THH_BACKEND_PROD_URL")
    else:
        raise ThhJdFetchError(
            f"unknown environment: {environment!r}", status_code=400
        )
    base = (override or os.getenv("THH_BACKEND_BASE_URL") or _DEFAULT_HOSTS[environment]).strip()
    return base.rstrip("/")


def _token_for_environment(environment: int) -> str:
    """Per-env service token. Legacy single-token var is the rollout fallback."""
    if environment == ENV_STAGE:
        env_specific = os.getenv("THH_BACKEND_SERVICE_TOKEN_STAGE")
    elif environment == ENV_PROD:
        env_specific = os.getenv("THH_BACKEND_SERVICE_TOKEN_PROD")
    else:
        env_specific = None
    token = (env_specific or os.getenv("THH_BACKEND_SERVICE_TOKEN") or "").strip()
    if not token:
        raise ThhJdFetchError(
            "service token not configured for this environment",
            status_code=503,
        )
    return token


def _headers(token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        # Match the X-Service-Token convention used by the existing
        # thh_backend.py module so HH-BE's verification path is uniform.
        "X-Service-Token": token,
        # Belt-and-suspenders: HH-BE accepts either header during rollout.
        "Authorization": f"Bearer {token}",
    }


async def fetch_full_job(thh_job_id: int, environment: int) -> dict:
    """Hit HH-BE's `/api/admin/jobs/<id>/full` for the supplied row.

    Returns the data envelope as-is so the LEADS route can pass it
    through to the FE without re-shaping. Raises `ThhJdFetchError` with
    an appropriate HTTP status code on any failure.
    """
    host = _host_for_environment(environment)
    token = _token_for_environment(environment)
    url = f"{host}/api/admin/jobs/{int(thh_job_id)}/full"
    logger.info(
        "thh.jd.fetch.request",
        extra={"thh_job_id": thh_job_id, "environment": environment, "host": host},
    )
    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers=_headers(token))
    except httpx.TimeoutException as exc:
        logger.warning(
            "thh.jd.fetch.timeout",
            extra={"thh_job_id": thh_job_id, "environment": environment},
        )
        raise ThhJdFetchError("upstream HH-BE timed out", status_code=504) from exc
    except httpx.RequestError as exc:
        logger.warning(
            "thh.jd.fetch.network_error",
            extra={"thh_job_id": thh_job_id, "environment": environment, "err": str(exc)},
        )
        raise ThhJdFetchError("upstream HH-BE unreachable", status_code=502) from exc

    if response.status_code == 401:
        raise ThhJdFetchError("HH-BE rejected our service token", status_code=502)
    if response.status_code == 404:
        raise ThhJdFetchError("job not found on HH-BE", status_code=404)
    if response.status_code >= 400:
        raise ThhJdFetchError(
            f"HH-BE returned {response.status_code}", status_code=502
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise ThhJdFetchError("HH-BE response was not JSON", status_code=502) from exc

    if not isinstance(body, dict) or not body.get("success"):
        raise ThhJdFetchError(
            "HH-BE response envelope missing or unsuccessful", status_code=502
        )
    data = body.get("data")
    if not isinstance(data, dict):
        raise ThhJdFetchError(
            "HH-BE response missing `data` payload", status_code=502
        )
    return data
