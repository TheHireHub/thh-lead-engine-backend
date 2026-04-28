"""FastAPI routes for signups (Schema doc §7.12, §9.3-9.4 OTP via thh-backend)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.common.envelope import ok

from .crud import SignupCRUD
from .enums import SIGNUP_REQUEST_TYPES, get_label
from .schemas import SignupCreate, SignupOut

router = APIRouter(prefix="/api/signups", tags=["signups"])


def _serialize(s) -> dict:
    out = SignupOut.model_validate(s).model_dump()
    out["request_type_label"] = get_label(SIGNUP_REQUEST_TYPES, s.request_type)
    return out


@router.get("/")
async def list_signups(limit: int = 100, db: AsyncSession = Depends(get_db)) -> dict:
    rows = await SignupCRUD.list_recent(db, limit=limit)
    return ok([_serialize(s) for s in rows])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_signup(payload: SignupCreate, db: AsyncSession = Depends(get_db)) -> dict:
    """
    TODO: integrate with thh-backend OTP send (Schema §9.3) — call thh-backend
    POST /api/auth/login-otp/send and write a campaign_event row event_type=otp_sent (16).
    """
    signup = await SignupCRUD.create(db, **payload.model_dump(exclude_none=True))
    return ok(_serialize(signup), message="signup recorded")


@router.post("/{signup_id}/otp-verify")
async def verify_otp(signup_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """
    TODO: integrate with thh-backend OTP verify (Schema §9.4). On success:
    - mark signup.otp_verified_at
    - upsert prospects via dedupe rules
    - move stage to next milestone
    - record campaign_event (otp_verified=17)
    - fire Telegram alert
    """
    signup = await SignupCRUD.get_by_id(db, signup_id)
    if not signup:
        raise HTTPException(status_code=404, detail="signup not found")
    signup = await SignupCRUD.mark_otp_verified(db, signup)
    return ok(_serialize(signup), message="otp verified")
