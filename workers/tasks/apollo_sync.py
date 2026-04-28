"""
Apollo sync task (Schema doc Arch-12, §9.2).

Pull-based, every 6 hours. Upserts prospects by `apollo_contact_id`.
Per Arch-12 we picked pull over webhook because Apollo webhooks are flaky.

Steps:
1. Page through Apollo /v1/people/search with our ICP filter
2. For each contact: call thh-backend `check-company-exists` (touch point #2)
3. Upsert into prospects via dedupe priority (LinkedIn > email > phone)
4. Touch ProspectChannel(channel=apollo)
5. Write audit_log for each insert/update
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def apollo_sync(ctx: dict) -> dict:
    """ARQ entrypoint."""
    logger.info("apollo_sync: TODO — implement page-through + upsert")
    return {"synced": 0}
