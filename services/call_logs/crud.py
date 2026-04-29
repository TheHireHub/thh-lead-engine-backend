"""
Async CRUD for call_logs.

The 3xRNR auto-marker (Schema doc §5.5, Arch-43) lives here: every insert
where outcome=rnr increments prospects.rnr_count; every time the count
reaches 3+ we write an audit_log entry. The exact "what happens to the
prospect" is P5 (PENDING USER INPUT) — see §14.

The Caller "Next prospect" workflow (§5.5) lives here too:
  - next_prospect_for_caller(caller_user_id) — picks the oldest-touched
    assigned prospect, excluding stages lost/unsubscribed/converted and
    excluding prospects with an RNR within the last 24h.
  - skip_prospect(prospect_id) — bumps prospects.last_touched_at so the
    same prospect doesn't reappear immediately.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.audit.crud import AuditLogCRUD
from services.prospects.models import Prospect

from .models import CallLog


# Stages excluded from the Caller "Next" pool (§6.2):
#   2 converted | 3 lost | 4 unsubscribed
EXCLUDED_STAGES = (2, 3, 4)


class CallLogCRUD:
    @staticmethod
    async def list_for_prospect(db: AsyncSession, prospect_id: int) -> list[CallLog]:
        result = await db.execute(
            select(CallLog)
            .where(CallLog.prospect_id == prospect_id)
            .order_by(CallLog.called_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_callbacks_for_caller(
        db: AsyncSession, caller_user_id: int, *, upcoming_only: bool = False
    ) -> list[CallLog]:
        stmt = select(CallLog).where(
            CallLog.caller_user_id == caller_user_id,
            CallLog.outcome == 2,  # call_back
            CallLog.callback_at.is_not(None),
        )
        if upcoming_only:
            stmt = stmt.where(CallLog.callback_at >= datetime.now(timezone.utc))
        stmt = stmt.order_by(CallLog.callback_at.asc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def record(db: AsyncSession, **fields) -> CallLog:
        """
        Insert a call log + apply 3xRNR auto-marker side-effect.

        On RNR insert: increment prospects.rnr_count. Whenever rnr_count
        reaches 3+, write an audit row action=auto_marked_not_interested.
        Always set prospects.last_touched_at = now so the Next-prospect
        query rotates the caller off this prospect.
        """
        log = CallLog(**fields)
        db.add(log)
        await db.flush()

        # Touch the prospect regardless of outcome.
        result = await db.execute(
            select(Prospect).where(Prospect.id == fields["prospect_id"])
        )
        prospect = result.scalar_one_or_none()
        if prospect:
            prospect.last_touched_at = datetime.now(timezone.utc)
            prospect.touch_count = (prospect.touch_count or 0) + 1

            if fields.get("outcome") == 0:  # rnr
                prospect.rnr_count = (prospect.rnr_count or 0) + 1
                if prospect.rnr_count >= 3:
                    # P5 PENDING (§14): decide whether to set a milestone
                    # column or move stage. For now: append-only audit row
                    # so the CSM/caller has visibility.
                    await AuditLogCRUD.record(
                        db,
                        entity_type="prospect",
                        entity_id=prospect.id,
                        action="auto_marked_not_interested",
                        actor_user_id=None,
                        after_json={"rnr_count": prospect.rnr_count},
                    )

        await db.commit()
        await db.refresh(log)
        return log

    @staticmethod
    async def next_prospect_for_caller(
        db: AsyncSession, caller_user_id: int
    ) -> Optional[Prospect]:
        """
        Pick the next prospect this caller should call.

        Rules (Schema doc §5.5):
        - Owned by this caller (prospects.owner_user_id == caller_user_id).
        - Not deleted.
        - Stage NOT IN (converted, lost, unsubscribed).
        - No RNR call_log within the last 24h (cool-off after a no-response).
        - Sort by last_touched_at ascending NULLs first (never-touched prospects
          surface before stale ones).
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        # Subquery: prospect_ids with an RNR in the last 24h.
        recent_rnr = (
            select(CallLog.prospect_id)
            .where(CallLog.outcome == 0, CallLog.called_at >= cutoff)
            .scalar_subquery()
        )

        # MySQL doesn't support NULLS FIRST — emulate with two-level sort:
        # rows where last_touched_at IS NULL come first, then by ASC.
        stmt = (
            select(Prospect)
            .where(
                Prospect.owner_user_id == caller_user_id,
                Prospect.deleted_at.is_(None),
                Prospect.stage.not_in(EXCLUDED_STAGES),
                Prospect.id.not_in(recent_rnr),
            )
            .order_by(
                Prospect.last_touched_at.is_(None).desc(),
                Prospect.last_touched_at.asc(),
            )
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def skip_prospect(db: AsyncSession, prospect_id: int) -> None:
        """Bump last_touched_at so the Next-prospect query rotates off this one."""
        result = await db.execute(
            select(Prospect).where(Prospect.id == prospect_id)
        )
        prospect = result.scalar_one_or_none()
        if prospect is not None:
            prospect.last_touched_at = datetime.now(timezone.utc)
            await db.commit()
