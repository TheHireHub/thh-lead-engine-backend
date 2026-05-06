"""FastAPI routes for call_logs (powers Caller "Next" view, Schema doc §5.5)."""

from __future__ import annotations

from datetime import date as date_t
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.crud import AdminUserCRUD
from services.admin_users.deps import (
    current_user,
    require_admin,
    require_caller,
    require_dashboard_read,
    require_sales_or_csm,
)
from services.admin_users.models import AdminUser
from services.audit.crud import AuditLogCRUD
from services.common.envelope import ok
from services.companies.models import Company
from services.prospects.enums import FUNNEL_STAGES
from services.prospects.enums import get_label as get_funnel_label
from services.prospects.models import Prospect

from .crud import CallLogCRUD
from .enums import CALL_OUTCOMES, get_label
from .models import CallLog
from .schemas import (
    CallLogCreate,
    CallLogOut,
    DailyStatsOut,
    NextProspectOut,
    QueueOut,
    QueueRow,
    SkipPayload,
)

router = APIRouter(prefix="/api/call-logs", tags=["call_logs"])


async def _company_name_map(db: AsyncSession, company_ids: list[int]) -> dict[int, str]:
    if not company_ids:
        return {}
    result = await db.execute(
        select(Company.id, Company.name).where(Company.id.in_(set(company_ids)))
    )
    return {int(cid): name for cid, name in result.all()}


async def _latest_outcome_map(
    db: AsyncSession, prospect_ids: list[int]
) -> dict[int, int]:
    """For each prospect, return the outcome of the most recent call_log row."""
    if not prospect_ids:
        return {}
    latest_at = (
        select(
            CallLog.prospect_id.label("pid"),
            func.max(CallLog.called_at).label("max_at"),
        )
        .where(CallLog.prospect_id.in_(set(prospect_ids)))
        .group_by(CallLog.prospect_id)
        .subquery()
    )
    stmt = (
        select(CallLog.prospect_id, CallLog.outcome)
        .join(
            latest_at,
            (CallLog.prospect_id == latest_at.c.pid)
            & (CallLog.called_at == latest_at.c.max_at),
        )
    )
    result = await db.execute(stmt)
    return {int(pid): int(outcome) for pid, outcome in result.all()}


async def _prospect_lookup_map(
    db: AsyncSession, prospect_ids: list[int]
) -> dict[int, tuple[Optional[str], Optional[int]]]:
    """For each prospect_id, return (display_name, company_id)."""
    if not prospect_ids:
        return {}
    result = await db.execute(
        select(Prospect.id, Prospect.first_name, Prospect.last_name, Prospect.company_id)
        .where(Prospect.id.in_(set(prospect_ids)))
    )
    out: dict[int, tuple[Optional[str], Optional[int]]] = {}
    for pid, fn, ln, cid in result.all():
        name = " ".join(p for p in [fn, ln] if p) or None
        out[int(pid)] = (name, int(cid) if cid is not None else None)
    return out


def _serialize(c, *, prospect_name: Optional[str] = None,
               company_id: Optional[int] = None,
               company_name: Optional[str] = None) -> dict:
    out = CallLogOut.model_validate(c).model_dump()
    out["outcome_label"] = get_label(CALL_OUTCOMES, c.outcome)
    out["prospect_name"] = prospect_name
    out["company_id"] = company_id
    out["company_name"] = company_name
    return out


async def _serialize_call_logs(db: AsyncSession, rows: list) -> list[dict]:
    """Enrich a list of CallLog rows with prospect_name + company_name (1 round-trip each)."""
    prospect_ids = [r.prospect_id for r in rows]
    prospect_map = await _prospect_lookup_map(db, prospect_ids)
    company_ids = [cid for _, cid in prospect_map.values() if cid is not None]
    company_map = await _company_name_map(db, company_ids)
    out = []
    for r in rows:
        name, cid = prospect_map.get(r.prospect_id, (None, None))
        out.append(_serialize(
            r,
            prospect_name=name,
            company_id=cid,
            company_name=company_map.get(cid) if cid is not None else None,
        ))
    return out


@router.get("/by-prospect/{prospect_id}")
async def list_for_prospect(
    prospect_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_sales_or_csm),
) -> dict:
    rows = await CallLogCRUD.list_for_prospect(db, prospect_id)
    return ok(await _serialize_call_logs(db, rows))


@router.get("/callbacks")
async def list_my_callbacks(
    upcoming_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_caller),
) -> dict:
    """Caller's own pending callbacks (Schema doc §5.5)."""
    rows = await CallLogCRUD.list_callbacks_for_caller(
        db, user.id, upcoming_only=upcoming_only
    )
    return ok(await _serialize_call_logs(db, rows))


@router.get("/callbacks/{caller_user_id}")
async def list_callbacks_for(
    caller_user_id: int,
    upcoming_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_admin),
) -> dict:
    """Admin-only — view another caller's callbacks."""
    rows = await CallLogCRUD.list_callbacks_for_caller(
        db, caller_user_id, upcoming_only=upcoming_only
    )
    return ok(await _serialize_call_logs(db, rows))


@router.get("/demos")
async def list_my_demos(
    upcoming_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_caller),
) -> dict:
    """Caller's own scheduled demos — outcome=demo_scheduled (4) with a
    callback_at time set. Powers the Sales Dashboard "Upcoming Demos" panel."""
    rows = await CallLogCRUD.list_calls_by_outcome_for_caller(
        db, user.id, outcome=4, upcoming_only=upcoming_only
    )
    return ok(await _serialize_call_logs(db, rows))


@router.get("/demos/{caller_user_id}")
async def list_demos_for(
    caller_user_id: int,
    upcoming_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_admin),
) -> dict:
    """Admin-only — view another caller's scheduled demos."""
    rows = await CallLogCRUD.list_calls_by_outcome_for_caller(
        db, caller_user_id, outcome=4, upcoming_only=upcoming_only
    )
    return ok(await _serialize_call_logs(db, rows))


# --- daily aggregates (Sales Dashboard / Prospects chips) -----------------

# CALL_OUTCOMES §6.26 keys, in canonical order. Every response always reports
# all five — missing outcomes are reported as 0 so the FE doesn't need a
# fallback path.
_OUTCOME_KEYS: list[str] = [
    "rnr",
    "not_interested",
    "call_back",
    "follow_up",
    "demo_scheduled",
    "demo_attended",
    "demo_no_show",
]


def _stage_serialize(
    prospect: Prospect,
    *,
    company_name: Optional[str] = None,
    last_outcome: Optional[int] = None,
) -> dict:
    name = " ".join(p for p in [prospect.first_name, prospect.last_name] if p) or None
    return {
        "prospect_id": prospect.id,
        "name": name,
        "title": prospect.title,
        "company_id": prospect.company_id,
        "company_name": company_name,
        "owner_user_id": prospect.owner_user_id,
        "phone": prospect.phone,
        "email": prospect.email,
        "stage": prospect.stage,
        "stage_label": get_funnel_label(FUNNEL_STAGES, prospect.stage),
        "last_outcome": last_outcome,
        "last_outcome_label": get_label(CALL_OUTCOMES, last_outcome) if last_outcome is not None else None,
        "last_touched_at": prospect.last_touched_at,
        "rnr_count": prospect.rnr_count,
    }


@router.get("/daily-stats")
async def daily_stats(
    date: Optional[date_t] = None,
    date_from: Optional[date_t] = None,
    date_to: Optional[date_t] = None,
    owner_user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    # Auth-only: callers (role 4) need access to their *own* daily-stats
    # for the "Next Prospect" view — the per-user check below already
    # blocks cross-rep snooping for non-admins (BUG-016).
    user: AdminUser = Depends(current_user),
) -> dict:
    """
    Per-caller call counters across `[date_from, date_to]` inclusive
    (powers Sales Dashboard KPI strip + Prospects-list call-stage chips).

    Param resolution:
      - `date_from` + `date_to` provided → use the window verbatim.
      - Only `date` provided (legacy) → single day window.
      - Nothing provided → today, single day.
    `target` scales linearly with the number of days in the window so the
    "calls today / target" ratio remains meaningful for week views.
    `owner_user_id` defaults to current user; only admin may inspect
    others (avoid cross-rep snooping per BUG-016).
    """
    today = datetime.now(timezone.utc).date()
    if date_from is not None or date_to is not None:
        # Range mode — fall back individually if only one bound was given.
        d_from = date_from or date_to or today
        d_to = date_to or date_from or today
    elif date is not None:
        d_from = d_to = date
    else:
        d_from = d_to = today

    if d_from > d_to:
        raise HTTPException(status_code=400, detail="date_from must be <= date_to")

    days_in_range = (d_to - d_from).days + 1

    # Admin "All" aggregate mode: admin requests stats with no rep filter →
    # we return org-wide counters (sum across every caller), with target
    # scaled by the number of active callers × days. Non-admin callers
    # always default to themselves (cross-rep snoop already 403s below).
    aggregate = owner_user_id is None and user.role == 0
    if aggregate:
        calls_today = await CallLogCRUD.calls_count_all_in_range(
            db, day_from=d_from, day_to=d_to
        )
        outcomes_raw = await CallLogCRUD.outcomes_all_in_range(
            db, day_from=d_from, day_to=d_to
        )
        in_queue = await CallLogCRUD.queue_size_all(db)
        # Sum daily_call_target across every active caller (role 4).
        callers = await AdminUserCRUD.list_all(db, role=4)
        per_day_target = sum((c.daily_call_target or 0) for c in callers)
        target = per_day_target * days_in_range
        caller_id_for_payload = 0  # sentinel — FE treats this as "aggregate"
    else:
        target_user_id = owner_user_id if owner_user_id is not None else user.id
        if target_user_id != user.id and user.role != 0:
            raise HTTPException(status_code=403, detail="cannot view other users' stats")
        target_user = await AdminUserCRUD.get_by_id(db, target_user_id)
        if target_user is None:
            raise HTTPException(status_code=404, detail="caller not found")
        calls_today = await CallLogCRUD.calls_count_in_range(
            db, caller_user_id=target_user_id, day_from=d_from, day_to=d_to
        )
        outcomes_raw = await CallLogCRUD.outcomes_in_range(
            db, caller_user_id=target_user_id, day_from=d_from, day_to=d_to
        )
        in_queue = await CallLogCRUD.queue_size_for_caller(
            db, caller_user_id=target_user_id
        )
        target = target_user.daily_call_target * days_in_range
        caller_id_for_payload = target_user_id

    by_outcome = {key: 0 for key in _OUTCOME_KEYS}
    for outcome_int, count in outcomes_raw.items():
        label = get_label(CALL_OUTCOMES, outcome_int)
        if label in by_outcome:
            by_outcome[label] = count

    payload = DailyStatsOut(
        caller_user_id=caller_id_for_payload,
        date=d_to,
        date_from=d_from,
        date_to=d_to,
        calls_today=calls_today,
        target=target,
        in_queue=in_queue,
        by_outcome=by_outcome,
    )
    return ok(payload.model_dump(mode="json"))


@router.get("/queue")
async def call_queue(
    owner_user_id: Optional[int] = None,
    date: Optional[date_t] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    # Auth-only: same reasoning as /daily-stats — caller must read their
    # own queue (BUG-016). Per-user check below covers non-admin scoping.
    user: AdminUser = Depends(current_user),
) -> dict:
    """
    Caller's eligible call queue (Schema doc §5.5 ordering — never-touched
    first, then oldest-touched). Returns a prospect snapshot per row.

    Defaults match `/daily-stats`: `date` → today (UTC, used only for the
    response payload), `owner_user_id` → current user. Non-admins may only
    request their own queue.
    """
    if date is None:
        date = datetime.now(timezone.utc).date()

    # Admin "All" aggregate mode (mirrors /daily-stats): admin with no rep
    # filter selected → org-wide queue across every eligible prospect.
    aggregate = owner_user_id is None and user.role == 0
    if aggregate:
        rows = await CallLogCRUD.queue_all(db, limit=limit, offset=offset)
        total = await CallLogCRUD.queue_size_all(db)
        target_user_id = 0  # sentinel
    else:
        target_user_id = owner_user_id if owner_user_id is not None else user.id
        if target_user_id != user.id and user.role != 0:
            raise HTTPException(status_code=403, detail="cannot view other users' queue")
        rows = await CallLogCRUD.queue_for_caller(
            db, caller_user_id=target_user_id, limit=limit, offset=offset
        )
        total = await CallLogCRUD.queue_size_for_caller(
            db, caller_user_id=target_user_id
        )
    company_ids = [p.company_id for p in rows if p.company_id is not None]
    company_map = await _company_name_map(db, company_ids)
    outcome_map = await _latest_outcome_map(db, [p.id for p in rows])
    payload = QueueOut(
        caller_user_id=target_user_id,
        date=date,
        total=total,
        rows=[
            QueueRow(**_stage_serialize(
                p,
                company_name=company_map.get(p.company_id) if p.company_id else None,
                last_outcome=outcome_map.get(p.id),
            ))
            for p in rows
        ],
    )
    return ok(payload.model_dump(mode="json"))


@router.get("/next-prospect")
async def next_prospect(
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_caller),
) -> dict:
    """
    Picks the next prospect this caller should call (Schema doc §5.5).
    Caller is the authenticated user.
    """
    prospect = await CallLogCRUD.next_prospect_for_caller(db, user.id)
    if prospect is None:
        return ok(None, message="no prospects in queue")
    payload = NextProspectOut(
        prospect_id=prospect.id,
        name=" ".join(p for p in [prospect.first_name, prospect.last_name] if p) or None,
        title=prospect.title,
        company_id=prospect.company_id,
        phone=prospect.phone,
        email=prospect.email,
        last_touched_at=prospect.last_touched_at,
        rnr_count=prospect.rnr_count,
    )
    return ok(payload.model_dump())


@router.post("/skip")
async def skip_prospect(
    payload: SkipPayload,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_caller),
) -> dict:
    """Bump prospect.last_touched_at so the same prospect doesn't reappear next."""
    await CallLogCRUD.skip_prospect(db, payload.prospect_id)
    return ok({"prospect_id": payload.prospect_id}, message="skipped")


@router.post("", status_code=status.HTTP_201_CREATED)
async def record_call(
    payload: CallLogCreate,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_caller),
) -> dict:
    """
    Caller records a call against a prospect. `caller_user_id` is taken
    from the authenticated user — clients cannot spoof another caller.
    """
    log = await CallLogCRUD.record(
        db,
        **payload.model_dump(exclude_none=True),
        caller_user_id=user.id,
    )
    await AuditLogCRUD.record(
        db,
        entity_type="call_log",
        entity_id=log.id,
        action="record",
        actor_user_id=log.caller_user_id,
        after_json={
            "prospect_id": log.prospect_id,
            "outcome": log.outcome,
            "outcome_label": get_label(CALL_OUTCOMES, log.outcome),
        },
    )
    return ok(_serialize(log), message="call recorded")
