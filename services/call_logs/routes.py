"""FastAPI routes for call_logs (powers Caller "Next" view, Schema doc §5.5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.deps import (
    require_admin,
    require_caller,
    require_sales_or_csm,
)
from services.admin_users.models import AdminUser
from services.audit.crud import AuditLogCRUD
from services.common.envelope import ok

from .crud import CallLogCRUD
from .enums import CALL_OUTCOMES, get_label
from .schemas import CallLogCreate, CallLogOut, NextProspectOut, SkipPayload

router = APIRouter(prefix="/api/call-logs", tags=["call_logs"])


def _serialize(c) -> dict:
    out = CallLogOut.model_validate(c).model_dump()
    out["outcome_label"] = get_label(CALL_OUTCOMES, c.outcome)
    return out


@router.get("/by-prospect/{prospect_id}")
async def list_for_prospect(
    prospect_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_sales_or_csm),
) -> dict:
    rows = await CallLogCRUD.list_for_prospect(db, prospect_id)
    return ok([_serialize(c) for c in rows])


@router.get("/callbacks")
async def list_my_callbacks(
    upcoming_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_caller),
) -> dict:
    """Caller's own pending callbacks (Schema doc §5.5)."""
    rows = await CallLogCRUD.list_callbacks_for_caller(
        db, user.id, upcoming_only=upcoming_only
    )
    return ok([_serialize(c) for c in rows])


@router.get("/callbacks/{caller_user_id}")
async def list_callbacks_for(
    caller_user_id: int,
    upcoming_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_admin),
) -> dict:
    """Admin-only — view another caller's callbacks."""
    rows = await CallLogCRUD.list_callbacks_for_caller(
        db, caller_user_id, upcoming_only=upcoming_only
    )
    return ok([_serialize(c) for c in rows])


@router.get("/next-prospect")
async def next_prospect(
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_caller),
) -> dict:
    """
    Picks the next prospect this caller should call (Schema doc §5.5).
    Caller is the authenticated user.
    """
    prospect = await CallLogCRUD.next_prospect_for_caller(db, user.id)
    if prospect is None:
        return ok(None, message="no prospects in queue")
    payload = NextProspectOut(
        prospect_id=prospect.id,
        name=" ".join(p for p in [prospect.first_name, prospect.last_name] if p) or None,
        title=prospect.title,
        company_id=prospect.company_id,
        phone=prospect.phone,
        email=prospect.email,
        last_touched_at=prospect.last_touched_at,
        rnr_count=prospect.rnr_count,
    )
    return ok(payload.model_dump())


@router.post("/skip")
async def skip_prospect(
    payload: SkipPayload,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_caller),
) -> dict:
    """Bump prospect.last_touched_at so the same prospect doesn't reappear next."""
    await CallLogCRUD.skip_prospect(db, payload.prospect_id)
    return ok({"prospect_id": payload.prospect_id}, message="skipped")


@router.post("/", status_code=status.HTTP_201_CREATED)
async def record_call(
    payload: CallLogCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_caller),
) -> dict:
    log = await CallLogCRUD.record(db, **payload.model_dump(exclude_none=True))
    await AuditLogCRUD.record(
        db,
        entity_type="call_log",
        entity_id=log.id,
        action="record",
        actor_user_id=log.caller_user_id,
        after_json={
            "prospect_id": log.prospect_id,
            "outcome": log.outcome,
            "outcome_label": get_label(CALL_OUTCOMES, log.outcome),
        },
    )
    return ok(_serialize(log), message="call recorded")
