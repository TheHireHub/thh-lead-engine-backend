"""
HTTP wrapper for the four / five touch points with thh-backend (Schema doc §9).

Phase 2 STATUS: stubs. Phase 3 (Dev A's lane) brings real httpx calls.
The function signatures below are the contract — Dev A should preserve them.

Touch points:
  §9.1  promote_prospect        — POST thh-backend LeadCRUD.create_lead
  §9.2  check_company_exists    — GET  thh-backend /api/.../check-company-exists
  §9.3  send_otp                — POST thh-backend /api/auth/login-otp/send
  §9.4  verify_otp              — POST thh-backend /api/auth/login-otp/verify
  §9.5  get_activation_status   — GET  thh-backend /api/lead-engine/activation-status

Until real impl ships, callers can pass `--stub` semantics: stubs always
"succeed" and return shape-compatible payloads so downstream code can run.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------- §9.1 (Phase 3)

async def promote_prospect(
    *,
    email: str,
    first_name: Optional[str],
    last_name: Optional[str],
    company_name: Optional[str],
    domain: Optional[str],
    phone: Optional[str],
    source: str,
    lead_engine_prospect_id: int,
) -> dict:
    """
    TODO Phase 3 (Dev A): real httpx POST to thh-backend's LeadCRUD.create_lead.
    Returns `{thh_user_id: int}` on success.
    """
    logger.info("[STUB] promote_prospect(%s) — Phase 3 will replace this", email)
    return {"thh_user_id": None, "_stub": True}


# --------------------------------------------------------------- §9.2 (Phase 3)

async def check_company_exists(*, email: str, domain: Optional[str]) -> dict:
    """
    TODO Phase 3 (Dev A): real call to thh-backend `check-company-exists`.
    Returns `{exists: bool, thh_user_id: int|None}`.
    """
    logger.info("[STUB] check_company_exists(%s, %s)", email, domain)
    return {"exists": False, "thh_user_id": None, "_stub": True}


# --------------------------------------------------------------- §9.3 (Phase 3)

async def send_otp(*, email: str, purpose: str = "lead_engine_signup") -> dict:
    """
    TODO Phase 3 (Dev A): real call to thh-backend POST /api/auth/login-otp/send.
    Returns `{success: bool, rate_limited: bool, retry_after: int|None}`.
    """
    logger.info("[STUB] send_otp(%s, %s)", email, purpose)
    return {"success": True, "rate_limited": False, "retry_after": None, "_stub": True}


# --------------------------------------------------------------- §9.4 (Phase 3)

async def verify_otp(*, email: str, otp_code: str) -> dict:
    """
    TODO Phase 3 (Dev A): real call to thh-backend POST /api/auth/login-otp/verify.
    Returns `{success: bool, reason: str|None}`.

    Stub semantics: any 6-digit code passes; anything else fails. This lets
    the signup flow be exercised end-to-end before Phase 3.
    """
    is_six_digits = otp_code.isdigit() and len(otp_code) == 6
    if is_six_digits:
        return {"success": True, "reason": None, "_stub": True}
    return {"success": False, "reason": "invalid otp format", "_stub": True}


# --------------------------------------------------------------- §9.5 (Phase 3)

async def get_activation_status(*, thh_user_id: int) -> dict:
    """
    TODO Phase 3 (Dev A): real call to thh-backend
    GET /api/lead-engine/activation-status?thh_user_id=X.

    Returns:
      {
        has_jobs: bool, job_count: int,
        has_applicants: bool, applicant_count: int,
        first_job_at: datetime|None, first_applicant_at: datetime|None,
      }
    """
    logger.info("[STUB] get_activation_status(thh_user_id=%s)", thh_user_id)
    return {
        "has_jobs": False,
        "job_count": 0,
        "has_applicants": False,
        "applicant_count": 0,
        "first_job_at": None,
        "first_applicant_at": None,
        "_stub": True,
    }


def thh_base_url() -> str:
    """Read on call, not on import — env may change between requests in dev."""
    return os.getenv("THH_BACKEND_BASE_URL", "http://localhost:5000")
