"""Async CRUD for campaigns + events."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Campaign, CampaignEvent, CampaignProspect


class CampaignCRUD:
    @staticmethod
    async def get_by_id(db: AsyncSession, campaign_id: int) -> Optional[Campaign]:
        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(db: AsyncSession, status: Optional[int] = None) -> list[Campaign]:
        stmt = select(Campaign).where(Campaign.deleted_at.is_(None))
        if status is not None:
            stmt = stmt.where(Campaign.status == status)
        result = await db.execute(stmt.order_by(Campaign.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, **fields) -> Campaign:
        campaign = Campaign(**fields)
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
        return campaign


class CampaignEventCRUD:
    @staticmethod
    async def record(db: AsyncSession, **fields) -> CampaignEvent:
        event = CampaignEvent(**fields)
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event

    @staticmethod
    async def list_for_prospect(db: AsyncSession, prospect_id: int) -> list[CampaignEvent]:
        result = await db.execute(
            select(CampaignEvent)
            .where(CampaignEvent.prospect_id == prospect_id)
            .order_by(CampaignEvent.occurred_at.desc())
        )
        return list(result.scalars().all())


class CampaignProspectCRUD:
    @staticmethod
    async def add_prospects(db: AsyncSession, campaign_id: int, prospect_ids: list[int]) -> int:
        for pid in prospect_ids:
            db.add(CampaignProspect(campaign_id=campaign_id, prospect_id=pid))
        await db.commit()
        return len(prospect_ids)
