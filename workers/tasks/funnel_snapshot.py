"""
Daily funnel snapshot task (Schema doc Arch-20, §7.17).

Aggregates today's prospect counts by (stage, channel, owner_user_id) and
writes them to funnel_daily_snapshots via INSERT ... ON DUPLICATE KEY
UPDATE so the job is idempotent.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def funnel_snapshot(ctx: dict) -> dict:
    """ARQ entrypoint."""
    logger.info("funnel_snapshot: TODO — group prospects by (stage, channel, owner) and upsert")
    return {"rows": 0}
