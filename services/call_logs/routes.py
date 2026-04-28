"""FastAPI routes for call_logs (powers Caller "Next" view, Schema doc §5.5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.common.envelope import ok

from .crud import CallLogCRUD
from .enums import CALL_OUTCOMES, get_label
from .schemas import CallLogCreate, CallLogOut

router = APIRouter(prefix="/api/call-logs", tags=["call_logs"])


def _serialize(c) -> dict:
    out = CallLogOut.model_validate(c).model_dump()
    out["outcome_label"] = get_label(CALL_OUTCOMES, c.outcome)
    return out


@router.get("/by-prospect/{prospect_id}")
async def list_for_prospect(prospect_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    rows = await CallLogCRUD.list_for_prospect(db, prospect_id)
    return ok([_serialize(c) for c in rows])


@router.get("/callbacks/{caller_user_id}")
async def list_callbacks(caller_user_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Caller's pending callbacks sub-view (Schema doc §5.5)."""
    rows = await CallLogCRUD.list_callbacks_for_caller(db, caller_user_id)
    return ok([_serialize(c) for c in rows])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def record_call(payload: CallLogCreate, db: AsyncSession = Depends(get_db)) -> dict:
    log = await CallLogCRUD.record(db, **payload.model_dump(exclude_none=True))
    return ok(_serialize(log), message="call recorded")
