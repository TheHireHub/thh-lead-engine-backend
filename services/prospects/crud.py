"""
Async CRUD for the prospects domain.

NOTE: stage transitions MUST go through `change_stage()` which writes both
the prospects.stage column and a prospect_stage_history row in one
transaction. Don't update prospects.stage directly elsewhere.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Prospect,
    ProspectChannel,
    ProspectMergeLog,
    ProspectMergeReviewQueue,
    ProspectStageHistory,
)


class ProspectCRUD:
    @staticmethod
    async def get_by_id(db: AsyncSession, prospect_id: int) -> Optional[Prospect]:
        result = await db.execute(
            select(Prospect).where(Prospect.id == prospect_id, Prospect.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_linkedin(db: AsyncSession, linkedin_url: str) -> Optional[Prospect]:
        result = await db.execute(select(Prospect).where(Prospect.linkedin_url == linkedin_url))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_apollo_id(db: AsyncSession, apollo_contact_id: str) -> Optional[Prospect]:
        result = await db.execute(select(Prospect).where(Prospect.apollo_contact_id == apollo_contact_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_stage(
        db: AsyncSession, stage: Optional[int] = None, limit: int = 100, offset: int = 0
    ) -> list[Prospect]:
        stmt = select(Prospect).where(Prospect.deleted_at.is_(None))
        if stage is not None:
            stmt = stmt.where(Prospect.stage == stage)
        stmt = stmt.order_by(Prospect.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, **fields) -> Prospect:
        prospect = Prospect(**fields)
        db.add(prospect)
        await db.commit()
        await db.refresh(prospect)
        return prospect

    @staticmethod
    async def update(db: AsyncSession, prospect: Prospect, **fields) -> Prospect:
        for key, value in fields.items():
            if value is not None:
                setattr(prospect, key, value)
        await db.commit()
        await db.refresh(prospect)
        return prospect

    @staticmethod
    async def soft_delete(db: AsyncSession, prospect: Prospect) -> None:
        prospect.deleted_at = datetime.now(timezone.utc)
        await db.commit()

    @staticmethod
    async def change_stage(
        db: AsyncSession,
        prospect: Prospect,
        *,
        to_stage: int,
        reason: Optional[str] = None,
        changed_by_user_id: Optional[int] = None,
    ) -> Prospect:
        """
        Atomically: update prospect.stage AND insert prospect_stage_history row.
        Use this — never set prospect.stage directly.
        """
        from_stage = prospect.stage
        prospect.stage = to_stage
        db.add(
            ProspectStageHistory(
                prospect_id=prospect.id,
                from_stage=from_stage,
                to_stage=to_stage,
                reason=reason,
                changed_by_user_id=changed_by_user_id,
            )
        )
        await db.commit()
        await db.refresh(prospect)
        return prospect


class ProspectChannelCRUD:
    @staticmethod
    async def upsert_touch(db: AsyncSession, prospect_id: int, channel: int) -> ProspectChannel:
        result = await db.execute(
            select(ProspectChannel).where(
                ProspectChannel.prospect_id == prospect_id,
                ProspectChannel.channel == channel,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = ProspectChannel(prospect_id=prospect_id, channel=channel, touch_count=1)
            db.add(row)
        else:
            row.touch_count += 1
            row.last_touched_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(row)
        return row


class ProspectMergeReviewCRUD:
    @staticmethod
    async def list_pending(db: AsyncSession, limit: int = 50) -> list[ProspectMergeReviewQueue]:
        stmt = (
            select(ProspectMergeReviewQueue)
            .where(ProspectMergeReviewQueue.status == 0)
            .order_by(ProspectMergeReviewQueue.created_at.asc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


class ProspectMergeLogCRUD:
    @staticmethod
    async def record_merge(
        db: AsyncSession,
        *,
        kept_prospect_id: int,
        merged_prospect_id: int,
        match_strategy: int,
        merged_by_user_id: Optional[int] = None,
        snapshot_json: Optional[dict] = None,
    ) -> ProspectMergeLog:
        row = ProspectMergeLog(
            kept_prospect_id=kept_prospect_id,
            merged_prospect_id=merged_prospect_id,
            match_strategy=match_strategy,
            merged_by_user_id=merged_by_user_id,
            snapshot_json=snapshot_json,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row
