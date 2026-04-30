"""
Async CRUD for funnel_daily_snapshots.

The unique key on (snapshot_date, stage, channel, owner_user_id) lets the
snapshot worker run idempotently via INSERT ... ON DUPLICATE KEY UPDATE
(Schema doc Arch-20).

The daily snapshot table is the historical source of truth; the "today"
endpoint reads live counts from `prospects` directly because the snapshot
worker only writes once per day.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from services.prospects.models import Prospect

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
        """
        Idempotent upsert into funnel_daily_snapshots.

        The table's uk_fds_dimension UNIQUE includes nullable columns
        (channel, owner_user_id). MySQL UNIQUE treats multiple NULLs as
        distinct, so ON DUPLICATE KEY UPDATE doesn't catch rollup rows
        where channel/owner are NULL. For those cases we emulate the
        upsert manually via SELECT-then-UPDATE-or-INSERT.
        """
        if channel is not None and owner_user_id is not None:
            # Both columns non-null — the unique key works as expected.
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
            return

        # Manual upsert for NULL-containing keys.
        find = select(FunnelDailySnapshot).where(
            FunnelDailySnapshot.snapshot_date == snapshot_date,
            FunnelDailySnapshot.stage == stage,
        )
        find = (
            find.where(FunnelDailySnapshot.channel == channel)
            if channel is not None
            else find.where(FunnelDailySnapshot.channel.is_(None))
        )
        find = (
            find.where(FunnelDailySnapshot.owner_user_id == owner_user_id)
            if owner_user_id is not None
            else find.where(FunnelDailySnapshot.owner_user_id.is_(None))
        )
        result = await db.execute(find)
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.prospect_count = prospect_count
        else:
            db.add(
                FunnelDailySnapshot(
                    snapshot_date=snapshot_date,
                    stage=stage,
                    channel=channel,
                    owner_user_id=owner_user_id,
                    prospect_count=prospect_count,
                )
            )
        await db.commit()

    @staticmethod
    async def list_by_date_range(
        db: AsyncSession,
        *,
        from_date: date,
        to_date: date,
        stage: Optional[int] = None,
        channel: Optional[int] = None,
    ) -> list[FunnelDailySnapshot]:
        stmt = select(FunnelDailySnapshot).where(
            FunnelDailySnapshot.snapshot_date >= from_date,
            FunnelDailySnapshot.snapshot_date <= to_date,
        )
        if stage is not None:
            stmt = stmt.where(FunnelDailySnapshot.stage == stage)
        if channel is not None:
            stmt = stmt.where(FunnelDailySnapshot.channel == channel)
        stmt = stmt.order_by(FunnelDailySnapshot.snapshot_date.asc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def today_live_counts_by_stage(db: AsyncSession) -> dict[int, int]:
        """
        Live counts from `prospects` grouped by stage. Used by the
        dashboard's "today's funnel" widget — snapshots are at most a day
        old, so this is fresher than reading the latest snapshot row.
        """
        stmt = (
            select(Prospect.stage, func.count(Prospect.id))
            .where(Prospect.deleted_at.is_(None))
            .group_by(Prospect.stage)
        )
        result = await db.execute(stmt)
        return {stage: count for stage, count in result.all()}

    @staticmethod
    async def milestone_counts(
        db: AsyncSession, *, from_date: date, to_date: date
    ) -> dict[str, int]:
        """
        Count of prospects whose milestone timestamp landed within the
        date range (Schema doc §3 — milestones fire in any order).
        """
        out: dict[str, int] = {}
        for col, key in (
            (Prospect.registered_at, "registered"),
            (Prospect.demo_booked_at, "demo_booked"),
            (Prospect.first_job_created_at, "first_job_created"),
            (Prospect.first_applicant_received_at, "first_applicant_received"),
            (Prospect.converted_at, "converted"),
        ):
            stmt = select(func.count(Prospect.id)).where(
                col.is_not(None),
                func.date(col) >= from_date,
                func.date(col) <= to_date,
                Prospect.deleted_at.is_(None),
            )
            result = await db.execute(stmt)
            out[key] = result.scalar_one() or 0
        return out

    @staticmethod
    async def daily_stage_series(
        db: AsyncSession, *, from_date: date, to_date: date, stage: int
    ) -> dict[date, int]:
        """
        Per-day prospect_count for a single stage across [from_date,
        to_date]. Sums all-channel (channel IS NULL) rollup rows so the
        result is the daily total.
        """
        stmt = (
            select(
                FunnelDailySnapshot.snapshot_date,
                func.sum(FunnelDailySnapshot.prospect_count),
            )
            .where(
                FunnelDailySnapshot.snapshot_date >= from_date,
                FunnelDailySnapshot.snapshot_date <= to_date,
                FunnelDailySnapshot.stage == stage,
                FunnelDailySnapshot.channel.is_(None),
            )
            .group_by(FunnelDailySnapshot.snapshot_date)
        )
        result = await db.execute(stmt)
        return {row[0]: int(row[1] or 0) for row in result.all()}

    @staticmethod
    async def daily_milestone_series(
        db: AsyncSession, *, from_date: date, to_date: date, milestone: str
    ) -> dict[date, int]:
        """
        Per-day count of prospects whose `<milestone>_at` timestamp falls
        on that calendar day. Cohort-style series — each prospect counts
        once per milestone hit (Schema doc §3 — milestones are
        independent timestamps).
        """
        col_map = {
            "registered": Prospect.registered_at,
            "demo_booked": Prospect.demo_booked_at,
            "first_job_created": Prospect.first_job_created_at,
            "first_applicant_received": Prospect.first_applicant_received_at,
            "converted": Prospect.converted_at,
        }
        col = col_map[milestone]
        bucket = func.date(col).label("bucket")
        stmt = (
            select(bucket, func.count(Prospect.id))
            .where(
                col.is_not(None),
                func.date(col) >= from_date,
                func.date(col) <= to_date,
                Prospect.deleted_at.is_(None),
            )
            .group_by(bucket)
        )
        result = await db.execute(stmt)
        return {row[0]: int(row[1] or 0) for row in result.all()}

    @staticmethod
    async def stage_totals_in_range(
        db: AsyncSession, *, from_date: date, to_date: date
    ) -> dict[int, int]:
        """
        Sum of `prospect_count` per stage across all all-channel rollup rows
        in the date range. Used to compute conversion rates.
        """
        stmt = (
            select(
                FunnelDailySnapshot.stage,
                func.sum(FunnelDailySnapshot.prospect_count),
            )
            .where(
                FunnelDailySnapshot.snapshot_date >= from_date,
                FunnelDailySnapshot.snapshot_date <= to_date,
                FunnelDailySnapshot.channel.is_(None),
            )
            .group_by(FunnelDailySnapshot.stage)
        )
        result = await db.execute(stmt)
        return {int(stage): int(total or 0) for stage, total in result.all()}
