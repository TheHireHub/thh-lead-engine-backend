"""
Async CRUD for campaigns + campaign_prospects + campaign_events.

Tables:
- §7.6  campaigns
- §7.7  campaign_prospects (junction)
- §7.8  campaign_events
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.environment import env_filter_clause

from .models import Campaign, CampaignEvent, CampaignProspect


class CampaignCRUD:
    @staticmethod
    async def get_by_id(db: AsyncSession, campaign_id: int) -> Optional[Campaign]:
        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession,
        status: Optional[int] = None,
        channel: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
        environment: Optional[int] = None,
    ) -> list[Campaign]:
        stmt = select(Campaign).where(Campaign.deleted_at.is_(None))
        if status is not None:
            stmt = stmt.where(Campaign.status == status)
        if channel is not None:
            stmt = stmt.where(Campaign.channel == channel)
        env_clause = env_filter_clause(Campaign.environment, environment)
        if env_clause is not None:
            stmt = stmt.where(env_clause)
        stmt = stmt.order_by(Campaign.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, **fields) -> Campaign:
        campaign = Campaign(**fields)
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
        return campaign

    @staticmethod
    async def update(db: AsyncSession, campaign: Campaign, **fields) -> Campaign:
        for key, value in fields.items():
            if value is not None:
                setattr(campaign, key, value)
        await db.commit()
        await db.refresh(campaign)
        return campaign

    @staticmethod
    async def change_status(db: AsyncSession, campaign: Campaign, *, status: int) -> Campaign:
        """Move through §6.5: 0 draft, 1 active, 2 paused, 3 completed, 4 archived."""
        campaign.status = status
        await db.commit()
        await db.refresh(campaign)
        return campaign

    @staticmethod
    async def soft_delete(db: AsyncSession, campaign: Campaign) -> None:
        campaign.deleted_at = datetime.now(timezone.utc)
        await db.commit()


class CampaignEventCRUD:
    @staticmethod
    async def record(db: AsyncSession, **fields) -> CampaignEvent:
        event = CampaignEvent(**fields)
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event

    @staticmethod
    async def list_for_prospect(
        db: AsyncSession, prospect_id: int, limit: int = 200
    ) -> list[CampaignEvent]:
        result = await db.execute(
            select(CampaignEvent)
            .where(CampaignEvent.prospect_id == prospect_id)
            .order_by(CampaignEvent.occurred_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_for_campaign(
        db: AsyncSession,
        campaign_id: int,
        event_type: Optional[int] = None,
        limit: int = 500,
    ) -> list[CampaignEvent]:
        stmt = select(CampaignEvent).where(CampaignEvent.campaign_id == campaign_id)
        if event_type is not None:
            stmt = stmt.where(CampaignEvent.event_type == event_type)
        stmt = stmt.order_by(CampaignEvent.occurred_at.desc()).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_event_type(db: AsyncSession, campaign_id: int) -> dict[int, int]:
        """For dashboards — open/click/reply rate calculation."""
        result = await db.execute(
            select(CampaignEvent.event_type, func.count(CampaignEvent.id))
            .where(CampaignEvent.campaign_id == campaign_id)
            .group_by(CampaignEvent.event_type)
        )
        return {int(et): int(n) for et, n in result.all()}


class CampaignProspectCRUD:
    @staticmethod
    async def add_prospects(
        db: AsyncSession, campaign_id: int, prospect_ids: list[int]
    ) -> tuple[int, int]:
        """
        Idempotent bulk add. Returns (added, skipped).

        Skips prospect_ids already in this campaign (composite PK violation
        is caught and ignored per row).
        """
        added = 0
        skipped = 0
        for pid in prospect_ids:
            try:
                async with db.begin_nested():
                    # SAVEPOINT per-prospect — without this, hitting a single
                    # duplicate rolls back EVERY prior insert in this batch
                    # (and expires every ORM instance the caller holds,
                    # triggering MissingGreenlet on later sync attribute
                    # access). Scoping to a savepoint keeps the rest atomic.
                    row = CampaignProspect(campaign_id=campaign_id, prospect_id=pid)
                    db.add(row)
                    await db.flush()
                added += 1
            except IntegrityError:
                skipped += 1
        await db.commit()
        return added, skipped

    @staticmethod
    async def list_for_campaign(
        db: AsyncSession,
        campaign_id: int,
        status: Optional[int] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[CampaignProspect]:
        stmt = select(CampaignProspect).where(CampaignProspect.campaign_id == campaign_id)
        if status is not None:
            stmt = stmt.where(CampaignProspect.status == status)
        stmt = stmt.order_by(CampaignProspect.added_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def set_status(
        db: AsyncSession, *, campaign_id: int, prospect_id: int, status: int
    ) -> Optional[CampaignProspect]:
        """Update §6.6 status: queued/sent/skipped/failed/unsubscribed."""
        result = await db.execute(
            select(CampaignProspect).where(
                CampaignProspect.campaign_id == campaign_id,
                CampaignProspect.prospect_id == prospect_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.status = status
        await db.commit()
        await db.refresh(row)
        return row
