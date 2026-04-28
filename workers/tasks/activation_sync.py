"""
Daily activation status sync (Schema doc Arch-38, §9.5).

For every prospect with `thh_user_id` set, calls thh-backend
GET /api/lead-engine/activation-status?thh_user_id=X and updates the
prospect's:
- first_job_created_at
- first_applicant_received_at
- jobs_created_count
- applicants_received_count

Fires Telegram alert on first-time activation.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def activation_sync(ctx: dict) -> dict:
    """ARQ entrypoint."""
    logger.info("activation_sync: TODO — call thh-backend §9.5 per promoted prospect")
    return {"checked": 0, "newly_activated": 0}
