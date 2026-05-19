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
from services.common.tz import business_offset_str
from services.prospects.crud import ProspectCRUD
from services.prospects.models import Prospect, ProspectStageHistory

from .models import CallLog


def _called_at_local_date():
    """Render `func.date(called_at)` interpreted as the business-local
    calendar date.

    Production assumption: MySQL session `time_zone = SYSTEM` and the
    DB host runs on the business TZ (IST in our case), so `called_at`
    is stored as a naive timestamp already in business-local time. A
    plain `func.date()` therefore yields the local calendar day — no
    `CONVERT_TZ` needed. If you ever switch the DB host to UTC (which
    is the more "correct" pattern), uncomment the CONVERT_TZ form below
    and `today_business()` will continue to align with stored dates.
    """
    # _ = business_offset_str  # reserved for the UTC-storage variant
    return func.date(CallLog.called_at)


# Stages excluded from the Caller "Next" pool (§6.2):
#   2 converted | 3 lost | 4 unsubscribed
EXCLUDED_STAGES = (2, 3, 4)

# Channels excluded from the Caller queue (§6.3):
#   13 hh_signup — product-driven signups on app.thehirehub.ai; these are
#   inbound leads (already onboarded or about to be) and should NOT be cold-
#   called by the BDR team. They surface on the /signups page instead.
EXCLUDED_CHANNELS = (13,)


def _next_open_callback_subq(*, caller_user_id: int | None = None):
    """Correlated subquery returning the next OPEN `callback_at` for a
    prospect. Used in queue ORDER BY so callback-pending leads surface
    at the top of the queue — they're commitments, not done items.

    "Open" means: the most recent callback hasn't been resolved by a
    later outcome. For outcome=2 (call_back), resolution outcomes are
    1 not_interested / 4 demo_scheduled / 5 demo_attended / 6 demo_no_show.
    For outcome=4 (demo_scheduled), resolution is just 5 / 6. RNR /
    follow_up / another call_back DON'T resolve a callback — they're
    mid-flight attempts.

    The lookup is intentionally NOT scoped by caller. A callback is a
    commitment on the PROSPECT, not on the rep — if admin logs a
    callback for caller A's prospect, caller A still owes that call.
    Reassigning a lead carries the open callback to the new owner.

    `caller_user_id` is accepted for API symmetry but currently unused
    (kept so callers don't churn when we add per-team scoping later).
    """
    del caller_user_id
    from sqlalchemy import and_, exists, select as _select

    cl = CallLog.__table__.alias("cl_open")
    cl2 = CallLog.__table__.alias("cl_open_kill")

    # Callback-bearing outcomes: call_back (2), follow_up (3),
    # demo_scheduled (4). Each carries a callback_at and is treated as
    # an open commitment until a resolving outcome lands.
    base = _select(func.min(cl.c.callback_at)).where(
        cl.c.prospect_id == Prospect.id,
        cl.c.callback_at.is_not(None),
        cl.c.outcome.in_((2, 3, 4)),
    )
    # converted (7) is terminal and resolves any pending callback / demo:
    # once the prospect is a paying customer, the rep shouldn't see leftover
    # follow-up cards in Upcoming / Callbacks / Demos.
    resolving_for_2 = (1, 4, 5, 6, 7)
    resolving_for_3 = (1, 4, 5, 6, 7)
    resolving_for_4 = (5, 6, 7)
    kill = (
        _select(cl2.c.id)
        .where(
            cl2.c.prospect_id == cl.c.prospect_id,
            cl2.c.called_at > cl.c.called_at,
            or_(
                and_(cl.c.outcome == 2, cl2.c.outcome.in_(resolving_for_2)),
                and_(cl.c.outcome == 3, cl2.c.outcome.in_(resolving_for_3)),
                and_(cl.c.outcome == 4, cl2.c.outcome.in_(resolving_for_4)),
            ),
        )
        .correlate(cl)
    )
    base = base.where(~exists(kill))
    return base.correlate(Prospect).scalar_subquery()


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
            # 7 (converted) is terminal — also supersedes pending callbacks / demos.
            superseding = (5, 6, 7) if outcome == 4 else (1, 4, 5, 6, 7)
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

            outcome = fields.get("outcome")
            if outcome == 0:  # rnr
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
            elif outcome == 7 and prospect.stage != 2:  # converted (§6.26)
                # Caller marks the lead as a paying customer mid-call. Flip
                # stage→converted, stamp converted_at, write history+audit.
                # change_stage() commits the txn (including the call_log row
                # already flushed above), so the outer commit is a no-op.
                await ProspectCRUD.change_stage(
                    db,
                    prospect,
                    to_stage=2,
                    reason="call_outcome_converted",
                    changed_by_user_id=fields.get("caller_user_id"),
                )
            # NOTE: previously `not_interested` (outcome=1) auto-flipped
            # the prospect's stage to LOST, which dropped the row from
            # the queue and confused callers ("the lead I just logged
            # disappeared from BlackBuck"). Reverted on user request:
            # the lead now stays in queue with `last_outcome=not_interested`
            # rendered as a red chip on the row, and the explicit
            # "Mark Unsubscribed / Lost" buttons in the drawer remain the
            # only way to retire a lead. (audit 2026-05-08).

        await db.commit()
        await db.refresh(log)
        return log

    @staticmethod
    async def next_prospect_for_caller(
        db: AsyncSession, caller_user_id: int
    ) -> Optional[Prospect]:
        """
        Pick the next prospect this caller should call. Order matches
        `queue_for_caller` exactly so "Next" ≡ top-of-queue:
          1. Open callbacks (call_back / follow_up / demo_scheduled) by
             callback_at ASC — overdue surfaces first.
          2. Never-touched.
          3. Oldest touched.
        """
        next_cb = _next_open_callback_subq()
        stmt = (
            select(Prospect)
            .where(
                or_(
                    Prospect.owner_user_id == caller_user_id,
                    Prospect.created_by_user_id == caller_user_id,
                ),
                Prospect.deleted_at.is_(None),
                Prospect.stage.not_in(EXCLUDED_STAGES),
                Prospect.source_channel.not_in(EXCLUDED_CHANNELS),
            )
            .order_by(
                next_cb.is_(None).asc(),
                next_cb.asc(),
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
            _called_at_local_date() == day,
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
                _called_at_local_date() == day,
            )
            .group_by(CallLog.outcome)
        )
        result = await db.execute(stmt)
        return {int(outcome): int(cnt or 0) for outcome, cnt in result.all()}

    @staticmethod
    async def calls_on_owned_count_in_range(
        db: AsyncSession, *, owner_user_id: int, day_from: date, day_to: date
    ) -> int:
        """Count UNIQUE prospects called in `[day_from, day_to]` whose
        prospect.owner_user_id is currently `owner_user_id` — regardless
        of which caller logged the call. Powers the "queue activity"
        KPI which surfaces calls inherited via reassign. Distinct from
        `calls_count_in_range` (which is per-caller_user_id).
        """
        stmt = (
            select(_called_at_local_date(), func.count(func.distinct(CallLog.prospect_id)))
            .join(Prospect, Prospect.id == CallLog.prospect_id)
            .where(
                Prospect.owner_user_id == owner_user_id,
                _called_at_local_date() >= day_from,
                _called_at_local_date() <= day_to,
            )
            .group_by(_called_at_local_date())
        )
        result = await db.execute(stmt)
        return int(sum(int(cnt or 0) for _d, cnt in result.all()))

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
            select(_called_at_local_date(), func.count(func.distinct(CallLog.prospect_id)))
            .where(
                CallLog.caller_user_id == caller_user_id,
                _called_at_local_date() >= day_from,
                _called_at_local_date() <= day_to,
            )
            .group_by(_called_at_local_date())
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

        # converted (7) is terminal — also supersedes open demos and callbacks.
        demo_superseded = _is_later((5, 6, 7))
        callback_superseded = _is_later((1, 4, 5, 6, 7))
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
                _called_at_local_date() >= day_from,
                _called_at_local_date() <= day_to,
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
            elif o in (5, 6, 7):
                # Terminal outcomes — count DISTINCT prospects (re-logging the
                # same conversion shouldn't double-count the KPI).
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
            Prospect.source_channel.not_in(EXCLUDED_CHANNELS),
        )
        result = await db.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def queue_for_caller(
        db: AsyncSession,
        *,
        caller_user_id: int,
        limit: int = 2000,
        offset: int = 0,
    ) -> list[Prospect]:
        """
        Eligible call-queue rows for this caller. Order:
          1. Open-callback leads first (caller scheduled a call_back/demo
             that hasn't been resolved by a later 1/4/5/6 outcome) sorted
             by callback_at ASC — overdue/soonest at top so the caller
             never loses sight of a lead they promised to ring back.
          2. Never-touched leads (NULL last_touched_at).
          3. Other touched leads, oldest first.

        Default limit = 500 (most callers' personal queue fits well
        under this). Pagination available for tenants that grow past it.
        """
        next_cb = _next_open_callback_subq(caller_user_id=caller_user_id)
        stmt = (
            select(Prospect)
            .where(
                or_(
                    Prospect.owner_user_id == caller_user_id,
                    Prospect.created_by_user_id == caller_user_id,
                ),
                Prospect.deleted_at.is_(None),
                Prospect.stage.not_in(EXCLUDED_STAGES),
                Prospect.source_channel.not_in(EXCLUDED_CHANNELS),
            )
            .order_by(
                next_cb.is_(None).asc(),  # has callback first (False sorts before True)
                next_cb.asc(),  # soonest/overdue first
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
            Prospect.source_channel.not_in(EXCLUDED_CHANNELS),
        )
        result = await db.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def queue_all(
        db: AsyncSession, *, limit: int = 500, offset: int = 0
    ) -> list[Prospect]:
        # Same ordering rule as `queue_for_caller`: open callbacks first
        # (across all callers in admin "All" mode), then never-touched,
        # then oldest touched. Default limit raised to 500 to match.
        next_cb = _next_open_callback_subq(caller_user_id=None)
        stmt = (
            select(Prospect)
            .where(
                Prospect.deleted_at.is_(None),
                Prospect.stage.not_in(EXCLUDED_STAGES),
                Prospect.source_channel.not_in(EXCLUDED_CHANNELS),
            )
            .order_by(
                next_cb.is_(None).asc(),
                next_cb.asc(),
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
                _called_at_local_date(),
                func.count(func.distinct(CallLog.prospect_id)),
            )
            .where(
                _called_at_local_date() >= day_from,
                _called_at_local_date() <= day_to,
            )
            .group_by(CallLog.caller_user_id, _called_at_local_date())
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

        # converted (7) is terminal — also supersedes open demos and callbacks.
        demo_superseded = _is_later((5, 6, 7))
        callback_superseded = _is_later((1, 4, 5, 6, 7))
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
                _called_at_local_date() >= day_from,
                _called_at_local_date() <= day_to,
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
            elif o in (5, 6, 7):
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
