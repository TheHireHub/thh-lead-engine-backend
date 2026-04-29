"""
Auto-promotion helpers for prospects (Schema doc Arch-37, §3 funnel).

DB-agnostic orchestration — used by Dev B's landing-page-visit handler to
fire `Cold → Curious` when a prospect visits a landing page (P4 pending lock).
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .crud import ProspectCRUD

# §6.2 stage ints
_STAGE_COLD = 0
_STAGE_CURIOUS = 1


async def promote_to_curious_on_visit(
    db: AsyncSession,
    prospect_id: int,
    *,
    changed_by_user_id: Optional[int] = None,
) -> bool:
    """
    Idempotent. If prospect.stage == cold(0), bump to curious(1) via
    `ProspectCRUD.change_stage` (which writes stage_history + audit).

    Returns True if a transition fired, False otherwise (already curious /
    converted / lost / unsubscribed / not found).

    Called from Dev B's `landing_page_visits` POST handler after a visit
    insert succeeds.
    """
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if prospect is None or prospect.stage != _STAGE_COLD:
        return False
    await ProspectCRUD.change_stage(
        db,
        prospect,
        to_stage=_STAGE_CURIOUS,
        reason="auto: landing page visit",
        changed_by_user_id=changed_by_user_id,
    )
    return True
