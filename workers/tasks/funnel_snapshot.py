"""
Daily funnel snapshot task (Schema doc Arch-20, §7.17).

Aggregates today's prospect counts by (stage, source_channel, owner_user_id)
and writes them to funnel_daily_snapshots via INSERT ... ON DUPLICATE KEY
UPDATE so the job is idempotent.

Also writes an all-channel rollup row (channel=NULL) per stage so the
dashboard's `/conversion-rates` endpoint has a single SUM target.

Schedule (in workers/settings.py): daily at 02:00 IST.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from database_connection.connection import AsyncSessionLocal
from services.funnel_snapshots.crud import FunnelSnapshotCRUD
from services.prospects.models import Prospect
from setup_database import import_all_models

# Register every service's models on Base.metadata so SQLAlchemy can
# resolve cross-service FKs when this task runs as an ARQ subprocess
# (the FastAPI app would have already done this, but the worker is
# imported by arq separately and the lazy ORM mapper config fails on
# unresolved FKs without the full registry).
import_all_models()

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


async def funnel_snapshot(ctx: dict) -> dict:
    """ARQ entrypoint. Idempotent — same-day re-runs overwrite, never duplicate."""
    today = datetime.now(IST).date()
    logger.info("funnel_snapshot: starting for %s", today)

    rows_written = 0

    async with AsyncSessionLocal() as db:
        # ---- Per (stage, channel, owner) grouping ----
        result = await db.execute(
            select(
                Prospect.stage,
                Prospect.source_channel,
                Prospect.owner_user_id,
                func.count(Prospect.id),
            )
            .where(Prospect.deleted_at.is_(None))
            .group_by(
                Prospect.stage, Prospect.source_channel, Prospect.owner_user_id
            )
        )
        per_dim = list(result.all())
        for stage, channel, owner_user_id, count in per_dim:
            await FunnelSnapshotCRUD.upsert(
                db,
                snapshot_date=today,
                stage=int(stage),
                channel=int(channel) if channel is not None else None,
                owner_user_id=int(owner_user_id) if owner_user_id is not None else None,
                prospect_count=int(count),
            )
            rows_written += 1

        # ---- All-channel rollup: channel=NULL, owner_user_id=NULL, per stage ----
        result = await db.execute(
            select(Prospect.stage, func.count(Prospect.id))
            .where(Prospect.deleted_at.is_(None))
            .group_by(Prospect.stage)
        )
        for stage, count in result.all():
            await FunnelSnapshotCRUD.upsert(
                db,
                snapshot_date=today,
                stage=int(stage),
                channel=None,
                owner_user_id=None,
                prospect_count=int(count),
            )
            rows_written += 1

    logger.info("funnel_snapshot: done; %d rows upserted for %s", rows_written, today)
    return {"snapshot_date": today.isoformat(), "rows": rows_written}
