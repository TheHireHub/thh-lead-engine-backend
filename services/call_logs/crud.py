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

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, or_, select
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
    async def list_calls_by_outcome_for_caller(
        db: AsyncSession,
        caller_user_id: int,
        outcome: int,
        *,
        upcoming_only: bool = False,
    ) -> list[CallLog]:
        """Generic helper — returns this caller's calls for a given outcome,
        with `callback_at` set, ordered ascending. Used for both the
        Callbacks panel (outcome=2) and the Demos panel (outcome=4) on the
        Sales Dashboard.

        Demos (outcome=4) are filtered to drop rows whose prospect already
        has a newer terminal demo outcome (5 demo_attended | 6 demo_no_show)
        — once a rep marks the demo done, the card should leave Upcoming so
        rapid re-clicks can't double-count (user complaint 2026-05-05)."""
        stmt = select(CallLog).where(
            CallLog.caller_user_id == caller_user_id,
            CallLog.outcome == outcome,
            CallLog.callback_at.is_not(None),
        )
        if upcoming_only:
            stmt = stmt.where(CallLog.callback_at >= datetime.now(timezone.utc))
        if outcome in (2, 4):
            # Correlated subquery: drop a demo_scheduled (4) row if a later
            # 5 / 6 exists for the same prospect — the demo's been resolved.
            # Drop a call_back (2) row if a later 1 / 4 / 5 / 6 exists — the
            # callback request was consumed (prospect either lost interest,
            # scheduled a demo, or completed one). RNR / follow_up / another
            # call_back DON'T consume a callback — those are mid-flight
            # attempts, not resolutions. Keeps Upcoming + KPI showing only
            # OPEN state (user request 2026-05-05 "remove from demo
            # scheduled when attended; check others").
            from sqlalchemy import and_
            cl2 = CallLog.__table__.alias("cl2")
            superseding = (5, 6) if outcome == 4 else (1, 4, 5, 6)
            stmt = stmt.where(
                ~select(cl2.c.id).where(
                    and_(
                        cl2.c.prospect_id == CallLog.prospect_id,
                        cl2.c.outcome.in_(superseding),
                        or_(
                            cl2.c.called_at > CallLog.called_at,
                            and_(
                                cl2.c.called_at == CallLog.called_at,
                                cl2.c.id > CallLog.id,
                            ),
                        ),
                    )
                ).exists()
            )
        stmt = stmt.order_by(CallLog.callback_at.asc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_callbacks_for_caller(
        db: AsyncSession, caller_user_id: int, *, upcoming_only: bool = False
    ) -> list[CallLog]:
        return await CallLogCRUD.list_calls_by_outcome_for_caller(
            db, caller_user_id, outcome=2, upcoming_only=upcoming_only
        )

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
        - Owned by this caller (prospects.owner_user_id == caller_user_id) OR
          created by this caller.
        - Not deleted.
        - Stage NOT IN (converted, lost, unsubscribed).
        - Sort by last_touched_at ascending NULLs first (never-touched prospects
          surface before stale ones). Recently-RNR'd leads sort last because
          their last_touched_at just got bumped, so they naturally fall to the
          bottom — but they STAY visible (caller decides whether to retry).
        """
        # MySQL doesn't support NULLS FIRST — emulate with two-level sort:
        # rows where last_touched_at IS NULL come first, then by ASC.
        # Caller scope: assigned-to-me OR added-by-me (§5.5 BDR isolation).
        stmt = (
            select(Prospect)
            .where(
                or_(
                    Prospect.owner_user_id == caller_user_id,
                    Prospect.created_by_user_id == caller_user_id,
                ),
                Prospect.deleted_at.is_(None),
                Prospect.stage.not_in(EXCLUDED_STAGES),
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
        """
        Count UNIQUE prospects this caller dialled on `day` (not raw
        call_log rows). Logging the same prospect twice in a day still
        counts as one against the daily target, so reps can't pad their
        number by re-logging the same lead.
        """
        stmt = select(func.count(func.distinct(CallLog.prospect_id))).where(
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
    async def calls_count_in_range(
        db: AsyncSession, *, caller_user_id: int, day_from: date, day_to: date
    ) -> int:
        """
        Same semantics as `calls_today_count` but across `[day_from, day_to]`
        inclusive. UNIQUE-prospect dedup is per-day so a prospect dialled on
        Mon AND Tue counts twice across the week (once per day) — matches
        what a manager wants to see when summing daily targets across a span.
        """
        stmt = (
            select(func.date(CallLog.called_at), func.count(func.distinct(CallLog.prospect_id)))
            .where(
                CallLog.caller_user_id == caller_user_id,
                func.date(CallLog.called_at) >= day_from,
                func.date(CallLog.called_at) <= day_to,
            )
            .group_by(func.date(CallLog.called_at))
        )
        result = await db.execute(stmt)
        return int(sum(int(cnt or 0) for _d, cnt in result.all()))

    @staticmethod
    async def outcomes_in_range(
        db: AsyncSession, *, caller_user_id: int, day_from: date, day_to: date
    ) -> dict[int, int]:
        """
        `{outcome_int: count}` summed across `[day_from, day_to]` inclusive.
        Per-outcome count semantics:
          - Terminal (5 attended, 6 no_show): DISTINCT prospect — historical.
          - Demo Scheduled (4): DISTINCT prospect AND no later 5/6 for the
            same prospect — open demos only (user 2026-05-05).
          - Callback (2): DISTINCT prospect AND no later 1/4/5/6 — open
            callbacks only. RNR/follow_up/another callback don't consume
            a callback (mid-flight attempts, not resolutions).
          - Everything else (rnr 0, not_interested 1, follow_up 3): raw
            row count (daily-activity stats; same prospect can legitimately
            be RNR'd or followed up multiple times).
        """
        from sqlalchemy import and_, case, null
        # Supersession check is org-wide (no caller_user_id filter on cl2):
        # if any caller marks the prospect as not_interested / demo_*, every
        # rep's earlier open-state row for that prospect is consumed. Mirrors
        # the same org-wide rule used by `list_calls_by_outcome_for_caller`.
        cl2 = CallLog.__table__.alias("cl2")
        # MySQL DATETIME(0) has 1-second resolution, so two outcomes logged
        # in the same second tie on `called_at` and a strict `>` would miss
        # the supersession (e.g. caller logs demo_scheduled then attended
        # within ~250ms — same second). Tie-break on `id` (monotonic).
        def _is_later(outcomes: tuple[int, ...]):
            return (
                select(cl2.c.id)
                .where(
                    and_(
                        cl2.c.prospect_id == CallLog.prospect_id,
                        cl2.c.outcome.in_(outcomes),
                        or_(
                            cl2.c.called_at > CallLog.called_at,
                            and_(
                                cl2.c.called_at == CallLog.called_at,
                                cl2.c.id > CallLog.id,
                            ),
                        ),
                    )
                )
                .exists()
            )

        demo_superseded = _is_later((5, 6))
        callback_superseded = _is_later((1, 4, 5, 6))
        demo_open_pid = case((~demo_superseded, CallLog.prospect_id), else_=null())
        callback_open_pid = case(
            (~callback_superseded, CallLog.prospect_id), else_=null()
        )
        stmt = (
            select(
                CallLog.outcome,
                func.count(CallLog.id).label("raw_count"),
                func.count(func.distinct(CallLog.prospect_id)).label("uniq_count"),
                func.count(func.distinct(demo_open_pid)).label("demo_open"),
                func.count(func.distinct(callback_open_pid)).label("callback_open"),
            )
            .where(
                CallLog.caller_user_id == caller_user_id,
                func.date(CallLog.called_at) >= day_from,
                func.date(CallLog.called_at) <= day_to,
            )
            .group_by(CallLog.outcome)
        )
        result = await db.execute(stmt)
        out: dict[int, int] = {}
        for outcome, raw, uniq, demo_open, cb_open in result.all():
            o = int(outcome)
            if o == 2:
                out[o] = int(cb_open or 0)
            elif o == 4:
                out[o] = int(demo_open or 0)
            elif o in (5, 6):
                out[o] = int(uniq or 0)
            else:
                out[o] = int(raw or 0)
        return out

    @staticmethod
    async def queue_size_for_caller(
        db: AsyncSession, *, caller_user_id: int
    ) -> int:
        """
        How many prospects this caller still has eligible to call right
        now. Same eligibility filter as `next_prospect_for_caller` but
        returning a count instead of one row.
        """
        stmt = select(func.count(Prospect.id)).where(
            or_(
                Prospect.owner_user_id == caller_user_id,
                Prospect.created_by_user_id == caller_user_id,
            ),
            Prospect.deleted_at.is_(None),
            Prospect.stage.not_in(EXCLUDED_STAGES),
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
        stmt = (
            select(Prospect)
            .where(
                or_(
                    Prospect.owner_user_id == caller_user_id,
                    Prospect.created_by_user_id == caller_user_id,
                ),
                Prospect.deleted_at.is_(None),
                Prospect.stage.not_in(EXCLUDED_STAGES),
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

    # --- admin "All" aggregate paths (no caller scope) --------------------
    # Used when an admin views the Sales Dashboard with no rep filter selected:
    # show every eligible prospect across the org, not just admin-owned ones.

    @staticmethod
    async def queue_size_all(db: AsyncSession) -> int:
        stmt = select(func.count(Prospect.id)).where(
            Prospect.deleted_at.is_(None),
            Prospect.stage.not_in(EXCLUDED_STAGES),
        )
        result = await db.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def queue_all(
        db: AsyncSession, *, limit: int = 100, offset: int = 0
    ) -> list[Prospect]:
        stmt = (
            select(Prospect)
            .where(
                Prospect.deleted_at.is_(None),
                Prospect.stage.not_in(EXCLUDED_STAGES),
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
    async def calls_count_all_in_range(
        db: AsyncSession, *, day_from: date, day_to: date
    ) -> int:
        """Sum of every caller's UNIQUE-prospect-per-day calls in the window."""
        stmt = (
            select(
                CallLog.caller_user_id,
                func.date(CallLog.called_at),
                func.count(func.distinct(CallLog.prospect_id)),
            )
            .where(
                func.date(CallLog.called_at) >= day_from,
                func.date(CallLog.called_at) <= day_to,
            )
            .group_by(CallLog.caller_user_id, func.date(CallLog.called_at))
        )
        result = await db.execute(stmt)
        return int(sum(int(cnt or 0) for _u, _d, cnt in result.all()))

    @staticmethod
    async def outcomes_all_in_range(
        db: AsyncSession, *, day_from: date, day_to: date
    ) -> dict[int, int]:
        """`{outcome_int: count}` summed across every caller in the window.
        Same per-outcome rules as `outcomes_in_range`. Difference: the
        supersession check is org-wide (any caller's later row counts)."""
        from sqlalchemy import and_, case, null
        cl2 = CallLog.__table__.alias("cl2")

        def _is_later(outcomes: tuple[int, ...]):
            return (
                select(cl2.c.id)
                .where(
                    and_(
                        cl2.c.prospect_id == CallLog.prospect_id,
                        cl2.c.outcome.in_(outcomes),
                        or_(
                            cl2.c.called_at > CallLog.called_at,
                            and_(
                                cl2.c.called_at == CallLog.called_at,
                                cl2.c.id > CallLog.id,
                            ),
                        ),
                    )
                )
                .exists()
            )

        demo_superseded = _is_later((5, 6))
        callback_superseded = _is_later((1, 4, 5, 6))
        demo_open_pid = case((~demo_superseded, CallLog.prospect_id), else_=null())
        callback_open_pid = case(
            (~callback_superseded, CallLog.prospect_id), else_=null()
        )
        stmt = (
            select(
                CallLog.outcome,
                func.count(CallLog.id).label("raw_count"),
                func.count(func.distinct(CallLog.prospect_id)).label("uniq_count"),
                func.count(func.distinct(demo_open_pid)).label("demo_open"),
                func.count(func.distinct(callback_open_pid)).label("callback_open"),
            )
            .where(
                func.date(CallLog.called_at) >= day_from,
                func.date(CallLog.called_at) <= day_to,
            )
            .group_by(CallLog.outcome)
        )
        result = await db.execute(stmt)
        out: dict[int, int] = {}
        for outcome, raw, uniq, demo_open, cb_open in result.all():
            o = int(outcome)
            if o == 2:
                out[o] = int(cb_open or 0)
            elif o == 4:
                out[o] = int(demo_open or 0)
            elif o in (5, 6):
                out[o] = int(uniq or 0)
            else:
                out[o] = int(raw or 0)
        return out

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
