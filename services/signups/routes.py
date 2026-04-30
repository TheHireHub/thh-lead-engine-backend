"""FastAPI routes for signups (Schema doc §7.12, §9.3-9.4 OTP via thh-backend)."""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.deps import require_internal
from services.admin_users.models import AdminUser
from services.audit.crud import AuditLogCRUD
from services.campaigns.crud import CampaignEventCRUD
from services.common.envelope import ok
from services.integrations import telegram, thh_backend
from services.landing_pages.crud import (
    LandingPageVariantCRUD,
    LandingPageVisitCRUD,
)
from services.prospects.crud import ProspectCRUD
from services.prospects.dedupe import find_existing

from .crud import SignupCRUD
from .enums import SIGNUP_REQUEST_TYPES, get_label
from .schemas import OtpVerifyPayload, SignupCreate, SignupOut

router = APIRouter(prefix="/api/signups", tags=["signups"])

# In-memory rate limiter for resend-otp.
# TODO: swap for redis-backed limiter in prod (gunicorn workers don't share dicts).
# Keyed by signup_id -> last send unix timestamp.
_RESEND_TS: dict[int, float] = {}
_RESEND_COOLDOWN_S = 60


def _serialize(s) -> dict:
    out = SignupOut.model_validate(s).model_dump()
    out["request_type_label"] = get_label(SIGNUP_REQUEST_TYPES, s.request_type)
    return out


@router.get("/")
async def list_signups(
    request_type: Optional[int] = None,
    otp_verified: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    rows = await SignupCRUD.list_filtered(
        db,
        request_type=request_type,
        otp_verified=otp_verified,
        limit=limit,
        offset=offset,
    )
    return ok([_serialize(s) for s in rows])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_signup(payload: SignupCreate, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Public endpoint. Called when a prospect submits the landing page form.

    Side effects:
    1. If visitor_id is provided, attach landing_page_id from the most recent
       visit (denormalised onto the signup for analytics).
    2. Insert signups row with otp_verified_at=NULL.
    3. Call thh-backend POST /api/auth/login-otp/send (md §9.3).
    4. Audit row.

    NOTE: campaign_events.otp_sent (16) is deferred until otp-verify because
    campaign_events.prospect_id is NOT NULL and the prospect doesn't exist
    yet. Both events get written once the prospect is upserted.
    """
    signup_fields = payload.model_dump(exclude_none=True)

    if payload.visitor_id:
        visit = await LandingPageVisitCRUD.latest_for_visitor(db, payload.visitor_id)
        if visit:
            signup_fields.setdefault("landing_page_id", visit.landing_page_id)

    signup = await SignupCRUD.create(db, **signup_fields)

    otp_resp = await thh_backend.send_otp(email=payload.email)
    if not otp_resp.get("success"):
        await AuditLogCRUD.record(
            db,
            entity_type="signup",
            entity_id=signup.id,
            action="otp_send_failed",
            after_json={"reason": otp_resp},
        )
    else:
        _RESEND_TS[signup.id] = time.time()

    await AuditLogCRUD.record(
        db,
        entity_type="signup",
        entity_id=signup.id,
        action="create",
        after_json={"email": signup.email, "visitor_id": signup.visitor_id},
    )
    return ok(_serialize(signup), message="signup recorded")


@router.post("/{signup_id}/resend-otp")
async def resend_otp(signup_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Rate-limited to 1 send per 60s per signup_id."""
    signup = await SignupCRUD.get_by_id(db, signup_id)
    if not signup:
        raise HTTPException(status_code=404, detail="signup not found")
    if signup.otp_verified_at:
        raise HTTPException(status_code=409, detail="signup already verified")

    last = _RESEND_TS.get(signup_id, 0.0)
    elapsed = time.time() - last
    if elapsed < _RESEND_COOLDOWN_S:
        retry_after = int(_RESEND_COOLDOWN_S - elapsed)
        raise HTTPException(
            status_code=429,
            detail=f"please wait {retry_after}s before requesting another OTP",
            headers={"Retry-After": str(retry_after)},
        )

    otp_resp = await thh_backend.send_otp(email=signup.email)
    _RESEND_TS[signup_id] = time.time()
    await AuditLogCRUD.record(
        db,
        entity_type="signup",
        entity_id=signup.id,
        action="otp_resend",
        after_json=otp_resp,
    )
    return ok({"sent": otp_resp.get("success", False)}, message="otp resent")


@router.post("/{signup_id}/otp-verify")
async def verify_otp(
    signup_id: int,
    payload: OtpVerifyPayload,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Verify OTP and complete signup. Per md §9.4 side effects:

    - Mark signup.otp_verified_at = now.
    - Attribute signup to landing_page_variant (bump signup_count).
    - Upsert prospect via Arch-6 dedupe priority (linkedin > email > phone).
      If new, create with email + name + phone from the signup row.
    - Attach signup -> prospect, set prospects.registered_at (md §3 milestone).
    - Write campaign_events otp_sent (16) + otp_verified (17) — deferred from
      signup creation because campaign_events.prospect_id is NOT NULL.
    - Telegram alert + audit row.
    """
    signup = await SignupCRUD.get_by_id(db, signup_id)
    if not signup:
        raise HTTPException(status_code=404, detail="signup not found")
    if signup.otp_verified_at:
        return ok(_serialize(signup), message="already verified")

    verify_resp = await thh_backend.verify_otp(
        email=signup.email, otp_code=payload.otp_code
    )
    if not verify_resp.get("success"):
        await AuditLogCRUD.record(
            db,
            entity_type="signup",
            entity_id=signup.id,
            action="otp_verify_failed",
            after_json=verify_resp,
        )
        raise HTTPException(status_code=400, detail=verify_resp.get("reason", "otp invalid"))

    signup = await SignupCRUD.mark_otp_verified(db, signup)

    # Attribute to variant.
    if signup.visitor_id:
        visit = await LandingPageVisitCRUD.latest_for_visitor(db, signup.visitor_id)
        if visit and visit.landing_page_variant_id:
            variant = await LandingPageVariantCRUD.get_by_id(
                db, visit.landing_page_variant_id
            )
            if variant:
                await LandingPageVariantCRUD.bump_signup(db, variant)

    # md Arch-6 dedupe priority + §9.4 upsert.
    if not signup.prospect_id:
        prospect = await find_existing(
            db, email=signup.email, phone=signup.phone
        )
        if prospect is None:
            first_name, last_name = (None, None)
            if signup.name:
                parts = signup.name.strip().split(" ", 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else None
            prospect = await ProspectCRUD.create(
                db,
                email=signup.email,
                phone=signup.phone,
                first_name=first_name,
                last_name=last_name,
            )
        await SignupCRUD.attach_prospect(db, signup, prospect.id)
        # md §3 — registered_at is the OTP-verified milestone.
        await ProspectCRUD.set_registered(db, prospect)

    # Write the deferred campaign_events (md §9.3 otp_sent=16, §9.4 otp_verified=17).
    if signup.prospect_id:
        for ev_type in (16, 17):
            await CampaignEventCRUD.record(
                db,
                prospect_id=signup.prospect_id,
                event_type=ev_type,
                payload_json={"signup_id": signup.id},
            )

    await telegram.send_alert(
        f"OTP verified: {signup.email} (signup #{signup.id})"
    )
    await AuditLogCRUD.record(
        db,
        entity_type="signup",
        entity_id=signup.id,
        action="otp_verified",
        after_json={"email": signup.email},
    )
    return ok(_serialize(signup), message="otp verified")
