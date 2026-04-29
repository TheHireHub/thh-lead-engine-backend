"""
Heat score recalculation (Schema doc Arch-21).

Rule (default, tunable):
    email open        +1   (event_type 2)
    email click       +2   (event_type 3)
    visit no signup   +3   (event_type 12)
    positive reply    +5   (event_type 5)

Bucket (§6.25):
    0-2  -> heat_level=0 cold
    3-7  -> heat_level=1 warm
    8+   -> heat_level=2 hot

Approach: full idempotent recompute.

Each run:
  1. Aggregate campaign_events grouped by (prospect_id, event_type).
  2. Sum the per-rule scores per prospect from the events table itself
     (events are the source of truth).
  3. Set prospects.heat_score = sum, prospects.heat_level = bucket(sum).

Why full recompute (not incremental):
  - Idempotent — no drift if synchronous heat increments diverge from rules.
  - Tolerates rule changes — bumping `open` from +1 to +2 just self-corrects
    on next run.
  - Cheap at MVP scale (millions of events at most; one GROUP BY).

Scheduled hourly (workers/settings.py).
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select, update

from database_connection.connection import AsyncSessionLocal
from services.campaigns.models import CampaignEvent
from services.prospects.models import Prospect

logger = logging.getLogger(__name__)


# Arch-21 rule (event_type § 6.7 -> score)
_EVENT_TYPE_SCORE: dict[int, int] = {
    2: 1,   # opened
    3: 2,   # clicked
    5: 5,   # replied_positive
    12: 3,  # landing_visit
}


def _bucket(score: int) -> int:
    if score >= 8:
        return 2
    if score >= 3:
        return 1
    return 0


async def heat_recalc(ctx: dict) -> dict:
    """
    ARQ entrypoint. Returns counters {prospects_scanned, prospects_updated}.
    """
    counters = {"prospects_scanned": 0, "prospects_updated": 0}

    async with AsyncSessionLocal() as db:
        # Aggregate counts per (prospect_id, event_type) over the full table.
        agg_stmt = (
            select(
                CampaignEvent.prospect_id,
                CampaignEvent.event_type,
                func.count(CampaignEvent.id).label("n"),
            )
            .group_by(CampaignEvent.prospect_id, CampaignEvent.event_type)
        )
        result = await db.execute(agg_stmt)
        # rollup -> {prospect_id: heat_score}
        scores: dict[int, int] = {}
        for prospect_id, event_type, n in result.all():
            score = _EVENT_TYPE_SCORE.get(int(event_type), 0)
            if score == 0:
                continue
            scores[int(prospect_id)] = scores.get(int(prospect_id), 0) + score * int(n)

        # Walk every prospect (so prospects with zero qualifying events get
        # zeroed out too, not just left at stale values).
        prospects = (await db.execute(
            select(Prospect.id, Prospect.heat_score, Prospect.heat_level)
            .where(Prospect.deleted_at.is_(None))
        )).all()

        for pid, current_score, current_level in prospects:
            counters["prospects_scanned"] += 1
            new_score = scores.get(int(pid), 0)
            new_level = _bucket(new_score)
            if new_score == int(current_score or 0) and new_level == int(current_level or 0):
                continue
            await db.execute(
                update(Prospect)
                .where(Prospect.id == pid)
                .values(heat_score=new_score, heat_level=new_level)
            )
            counters["prospects_updated"] += 1

        await db.commit()

    logger.info("heat_recalc done: %s", counters)
    return counters
