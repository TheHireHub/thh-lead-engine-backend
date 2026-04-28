"""
Heat score recalculation (Schema doc Arch-21).

Rule (default, tunable):
- email open       +1
- email click      +2
- visit no signup  +3
- positive reply   +5

Bucket:
- 0-2  -> heat_level=cold
- 3-7  -> heat_level=warm
- 8+   -> heat_level=hot

Walks `campaign_events` since last run, increments `prospects.heat_score`,
recomputes `prospects.heat_level`.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def heat_recalc(ctx: dict) -> dict:
    """ARQ entrypoint."""
    logger.info("heat_recalc: TODO — replay events since last_run, bump heat_score, rebucket heat_level")
    return {"updated": 0}
