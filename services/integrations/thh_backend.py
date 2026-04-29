"""
thh-backend HTTP client (Schema doc §9 — five touch points).

DB-agnostic per CLAUDE.md "Integrations" rules.

This is the ONLY module in lead-engine that talks to thh-backend. The five
touch points (§9.1-§9.5) are exposed as small, named functions so callers
do not duplicate URL strings or auth headers.

Currently implemented:
- §9.1 promote_lead       (called by promote-to-THH route)
- §9.2 check_company_exists (called by Apollo sync worker)
- §9.3 send_otp           (called by signups route)         [Dev B]
- §9.4 verify_otp         (called by signups route)         [Dev B]
- §9.5 get_activation_status (called by activation_sync worker) [Dev B]

Each function fails closed: HTTPStatusError on non-2xx, RequestError on
network failure. Callers decide whether to swallow or re-raise.

Env:
    THH_BACKEND_BASE_URL         — base URL (e.g. http://localhost:5000)
    THH_BACKEND_SERVICE_TOKEN    — service-to-service bearer token
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


def _base_url() -> str:
    return os.getenv("THH_BACKEND_BASE_URL", "http://localhost:5000").rstrip("/")


def _headers() -> dict[str, str]:
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    token = os.getenv("THH_BACKEND_SERVICE_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _post(path: str, *, json_body: dict[str, Any], timeout: float = 15.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(_base_url() + path, json=json_body, headers=_headers())
        resp.raise_for_status()
        return resp.json()


async def _get(path: str, *, params: Optional[dict] = None, timeout: float = 15.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(_base_url() + path, params=params, headers=_headers())
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# §9.1 Promote prospect to THH
# ---------------------------------------------------------------------------
async def promote_lead(
    *,
    email: str,
    first_name: str,
    last_name: Optional[str],
    company_name: Optional[str],
    domain: Optional[str],
    phone: Optional[str],
    source: str,
    lead_engine_prospect_id: int,
) -> dict:
    """
    Hit thh-backend's lead-create endpoint. Returns the response body —
    expected shape `{users.id, ...}` per md §9.1.

    Caller must persist `users.id` onto `prospects.thh_user_id`.
    """
    payload = {
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "company_name": company_name,
        "domain": domain,
        "phone": phone,
        "source": source,
        "lead_engine_prospect_id": lead_engine_prospect_id,
    }
    return await _post("/api/lead-engine/leads", json_body=payload)


# ---------------------------------------------------------------------------
# §9.2 Pre-import dedupe check
# ---------------------------------------------------------------------------
async def check_company_exists(*, email: Optional[str] = None, domain: Optional[str] = None) -> dict:
    """
    Returns `{exists: bool, thh_user_id?: int}` per md §9.2.

    Side-effect rule: if `exists=true`, the caller annotates the prospect
    (sets `prospects.thh_user_id`) but does NOT block the import.
    """
    params: dict[str, Any] = {}
    if email:
        params["email"] = email
    if domain:
        params["domain"] = domain
    return await _get("/api/lead-engine/check-company-exists", params=params)


# ---------------------------------------------------------------------------
# §9.3 Send OTP                                                  [Dev B uses]
# ---------------------------------------------------------------------------
async def send_otp(*, email: str, purpose: str = "lead_engine_signup") -> dict:
    return await _post("/api/auth/login-otp/send", json_body={"email": email, "purpose": purpose})


# ---------------------------------------------------------------------------
# §9.4 Verify OTP                                                [Dev B uses]
# ---------------------------------------------------------------------------
async def verify_otp(*, email: str, otp_code: str) -> dict:
    return await _post(
        "/api/auth/login-otp/verify", json_body={"email": email, "otp_code": otp_code}
    )


# ---------------------------------------------------------------------------
# §9.5 Activation status                                         [Dev B uses]
# ---------------------------------------------------------------------------
async def get_activation_status(*, thh_user_id: int) -> dict:
    """
    Returns `{has_jobs, job_count, has_applicants, applicant_count,
    first_job_at, first_applicant_at}` per md §9.5.
    """
    return await _get(
        "/api/lead-engine/activation-status", params={"thh_user_id": thh_user_id}
    )
