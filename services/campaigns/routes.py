"""FastAPI routes for campaigns + events."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.common.envelope import ok

from .crud import CampaignCRUD, CampaignEventCRUD
from .enums import CAMPAIGN_STATUSES, CHANNELS, get_label
from .schemas import CampaignCreate, CampaignEventCreate, CampaignOut

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


def _serialize(c) -> dict:
    out = CampaignOut.model_validate(c).model_dump()
    out["channel_label"] = get_label(CHANNELS, c.channel)
    out["status_label"] = get_label(CAMPAIGN_STATUSES, c.status)
    return out


@router.get("/")
async def list_campaigns(status: int | None = None, db: AsyncSession = Depends(get_db)) -> dict:
    rows = await CampaignCRUD.list_all(db, status=status)
    return ok([_serialize(c) for c in rows])


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    campaign = await CampaignCRUD.get_by_id(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")
    return ok(_serialize(campaign))


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate, created_by_user_id: int, db: AsyncSession = Depends(get_db)
) -> dict:
    # TODO: replace `created_by_user_id` query param with current user dependency once auth lands.
    campaign = await CampaignCRUD.create(
        db, **payload.model_dump(), created_by_user_id=created_by_user_id
    )
    return ok(_serialize(campaign), message="campaign created")


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def record_event(payload: CampaignEventCreate, db: AsyncSession = Depends(get_db)) -> dict:
    event = await CampaignEventCRUD.record(db, **payload.model_dump(exclude_none=True))
    return ok({"id": event.id}, message="event recorded")
