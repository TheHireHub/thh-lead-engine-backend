"""
Async CRUD for funnel_daily_snapshots.

The unique key on (snapshot_date, stage, channel, owner_user_id) lets the
snapshot worker run idempotently via INSERT ... ON DUPLICATE KEY UPDATE
(Schema doc Arch-20).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import FunnelDailySnapshot


class FunnelSnapshotCRUD:
    @staticmethod
    async def upsert(
        db: AsyncSession,
        *,
        snapshot_date: date,
        stage: int,
        prospect_count: int,
        channel: Optional[int] = None,
        owner_user_id: Optional[int] = None,
    ) -> None:
        stmt = mysql_insert(FunnelDailySnapshot).values(
            snapshot_date=snapshot_date,
            stage=stage,
            channel=channel,
            owner_user_id=owner_user_id,
            prospect_count=prospect_count,
        )
        stmt = stmt.on_duplicate_key_update(prospect_count=prospect_count)
        await db.execute(stmt)
        await db.commit()

    @staticmethod
    async def list_by_date_range(
        db: AsyncSession,
        *,
        from_date: date,
        to_date: date,
        stage: Optional[int] = None,
    ) -> list[FunnelDailySnapshot]:
        stmt = select(FunnelDailySnapshot).where(
            FunnelDailySnapshot.snapshot_date >= from_date,
            FunnelDailySnapshot.snapshot_date <= to_date,
        )
        if stage is not None:
            stmt = stmt.where(FunnelDailySnapshot.stage == stage)
        stmt = stmt.order_by(FunnelDailySnapshot.snapshot_date.asc())
        result = await db.execute(stmt)
        return list(result.scalars().all())
