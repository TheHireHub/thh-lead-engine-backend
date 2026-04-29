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

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
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

    # --- per-rep daily aggregates (Sales Dashboard / Prospects chips) -------

    @staticmethod
    async def calls_today_count(
        db: AsyncSession, *, caller_user_id: int, day: date
    ) -> int:
        """COUNT(*) of call_logs by this caller on `day`."""
        stmt = select(func.count(CallLog.id)).where(
            CallLog.caller_user_id == caller_user_id,
            func.date(CallLog.called_at) == day,
        )
        result = await db.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def outcomes_by_caller_on_date(
        db: AsyncSession, *, caller_user_id: int, day: date
    ) -> dict[int, int]:
        """
        `{outcome_int: count}` for the caller on `day`. Keys map into
        CALL_OUTCOMES (§6.26): 0 rnr | 1 not_interested | 2 call_back |
        3 follow_up | 4 demo_scheduled.
        """
        stmt = (
            select(CallLog.outcome, func.count(CallLog.id))
            .where(
                CallLog.caller_user_id == caller_user_id,
                func.date(CallLog.called_at) == day,
            )
            .group_by(CallLog.outcome)
        )
        result = await db.execute(stmt)
        return {int(outcome): int(cnt or 0) for outcome, cnt in result.all()}

    @staticmethod
    async def queue_size_for_caller(
        db: AsyncSession, *, caller_user_id: int
    ) -> int:
        """
        How many prospects this caller still has eligible to call right
        now. Same eligibility filter as `next_prospect_for_caller` but
        returning a count instead of one row.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_rnr = (
            select(CallLog.prospect_id)
            .where(CallLog.outcome == 0, CallLog.called_at >= cutoff)
            .scalar_subquery()
        )
        stmt = select(func.count(Prospect.id)).where(
            Prospect.owner_user_id == caller_user_id,
            Prospect.deleted_at.is_(None),
            Prospect.stage.not_in(EXCLUDED_STAGES),
            Prospect.id.not_in(recent_rnr),
        )
        result = await db.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def queue_for_caller(
        db: AsyncSession,
        *,
        caller_user_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Prospect]:
        """
        Eligible call-queue rows for this caller, ordered the same way
        `next_prospect_for_caller` picks: never-touched first (NULL
        last_touched_at), then oldest touched.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_rnr = (
            select(CallLog.prospect_id)
            .where(CallLog.outcome == 0, CallLog.called_at >= cutoff)
            .scalar_subquery()
        )
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
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def latest_per_prospect(
        db: AsyncSession, prospect_ids: list[int]
    ) -> dict[int, CallLog]:
        """
        For each `prospect_id` in `prospect_ids`, return the most recent
        `call_logs` row (the one driving FE "latest call stage" badges).
        Empty input → empty dict.
        """
        if not prospect_ids:
            return {}

        # MAX(called_at) per prospect_id → join back for the full row.
        latest_subq = (
            select(
                CallLog.prospect_id,
                func.max(CallLog.called_at).label("latest_at"),
            )
            .where(CallLog.prospect_id.in_(prospect_ids))
            .group_by(CallLog.prospect_id)
            .subquery()
        )
        stmt = select(CallLog).join(
            latest_subq,
            (CallLog.prospect_id == latest_subq.c.prospect_id)
            & (CallLog.called_at == latest_subq.c.latest_at),
        )
        result = await db.execute(stmt)
        out: dict[int, CallLog] = {}
        for row in result.scalars().all():
            # Tie-break on duplicate (called_at) — keep highest id (= latest insert).
            existing = out.get(row.prospect_id)
            if existing is None or row.id > existing.id:
                out[row.prospect_id] = row
        return out
