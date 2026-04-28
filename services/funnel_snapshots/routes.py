"""FastAPI routes for funnel snapshots (powers the dashboard)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.common.envelope import ok

from .crud import FunnelSnapshotCRUD
from .enums import CHANNELS, FUNNEL_STAGES, get_label
from .schemas import SnapshotOut

router = APIRouter(prefix="/api/funnel-snapshots", tags=["funnel_snapshots"])


def _serialize(s) -> dict:
    out = SnapshotOut.model_validate(s).model_dump()
    out["stage_label"] = get_label(FUNNEL_STAGES, s.stage)
    if s.channel is not None:
        out["channel_label"] = get_label(CHANNELS, s.channel)
    return out


@router.get("/")
async def list_snapshots(
    from_date: date = Query(...),
    to_date: date = Query(...),
    stage: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = await FunnelSnapshotCRUD.list_by_date_range(
        db, from_date=from_date, to_date=to_date, stage=stage
    )
    return ok([_serialize(s) for s in rows])
