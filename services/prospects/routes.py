"""FastAPI routes for prospects (Schema doc §7.3-§7.5, §7.19-§7.20, Arch-6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.crud import AdminUserCRUD
from services.admin_users.deps import (
    require_admin,
    require_dashboard_read,
    require_growth_or_bdr,
    require_internal,
    require_sales,
)
from services.admin_users.models import AdminUser
from services.audit.crud import AuditLogCRUD
from services.call_logs.crud import CallLogCRUD
from services.call_logs.enums import CALL_OUTCOMES
from services.call_logs.enums import get_label as get_outcome_label
from services.common.envelope import ok
from services.email_replies.enums import (
    REPLY_CLASSIFICATIONS,
    REPLY_CLASSIFIED_BY,
)
from services.email_replies.enums import get_label as get_reply_label

from .crud import (
    ProspectCRUD,
    ProspectMergeLogCRUD,
    ProspectMergeReviewCRUD,
)
from .dedupe import find_existing
from .enums import CHANNELS, FUNNEL_STAGES, get_label
from .quality import compute_quality_score
from .schemas import (
    MergeDecision,
    ProspectCreate,
    ProspectOut,
    ProspectUpdate,
    StageChange,
    TouchRequest,
)

router = APIRouter(prefix="/api/prospects", tags=["prospects"])

# A callback (outcome=2) within this window of `now` flips `is_urgent` true
# — drives the red follow-up pill on the Prospects list (BACKEND_CHANGES_PENDING #9b).
_URGENT_WINDOW = timedelta(minutes=60)


def _serialize(p, owner_names: dict[int, str] | None = None) -> dict:
    out = ProspectOut.model_validate(p).model_dump(mode="json")
    out["stage_label"] = get_label(FUNNEL_STAGES, p.stage)
    out["source_channel_label"] = get_label(CHANNELS, p.source_channel)
    if owner_names is not None and p.owner_user_id is not None:
        out["owner_name"] = owner_names.get(p.owner_user_id)
    return out


def _attach_latest_call(out: dict, call_log) -> None:
    """
    Fold the most recent `call_logs` row into a serialized prospect dict
    (in place). Sets `latest_call_*` keys + `is_urgent`. Always assigns
    the keys (None / False when no call) so FE doesn't have to handle
    presence/absence.
    """
    if call_log is None:
        out["latest_call_outcome"] = None
        out["latest_call_stage"] = None
        out["latest_call_follow_up_time"] = None
        out["latest_call_at"] = None
        out["is_urgent"] = False
        return

    outcome_label = get_outcome_label(CALL_OUTCOMES, call_log.outcome)
    follow_up = call_log.callback_at
    out["latest_call_outcome"] = call_log.outcome
    out["latest_call_stage"] = outcome_label
    out["latest_call_follow_up_time"] = (
        follow_up.isoformat() if follow_up is not None else None
    )
    out["latest_call_at"] = (
        call_log.called_at.isoformat() if call_log.called_at else None
    )

    is_urgent = False
    if call_log.outcome == 2 and follow_up is not None:  # call_back §6.26
        # Treat an aware/naive callback timestamp uniformly.
        target = follow_up if follow_up.tzinfo else follow_up.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        is_urgent = target <= now + _URGENT_WINDOW
    out["is_urgent"] = is_urgent


def _audit_payload(p) -> dict:
    return {
        "stage": p.stage,
        "heat_level": p.heat_level,
        "heat_score": p.heat_score,
        "source_channel": p.source_channel,
        "owner_user_id": p.owner_user_id,
    }


async def _quality_for_prospect(db: AsyncSession, prospect) -> int:
    """Look up company (if any) and compute Arch-22 quality score."""
    company = None
    if prospect.company_id:
        from services.companies.crud import CompanyCRUD

        company = await CompanyCRUD.get_by_id(db, prospect.company_id)
    return compute_quality_score(
        title=prospect.title,
        company_size=getattr(company, "size", None),
        company_funding_stage=getattr(company, "funding_stage", None),
    )


@router.get("")
async def list_prospects(
    stage: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """
    List prospects. Each row is enriched with `latest_call_*` fields +
    `is_urgent` from the most recent `call_logs` row (one batch query —
    no N+1) so the FE Prospects list can render the call-stage chip
    without a second round-trip. See BACKEND_CHANGES_PENDING.md item 9b.
    """
    prospects = await ProspectCRUD.list_by_stage(db, stage=stage, limit=limit, offset=offset)
    owner_ids = [p.owner_user_id for p in prospects if p.owner_user_id is not None]
    owner_names = await AdminUserCRUD.names_by_ids(db, owner_ids)
    rows = [_serialize(p, owner_names) for p in prospects]
    if prospects:
        latest = await CallLogCRUD.latest_per_prospect(db, [p.id for p in prospects])
        for row, prospect in zip(rows, prospects):
            _attach_latest_call(row, latest.get(prospect.id))
    return ok(rows)


@router.get("/merge-review/pending")
async def list_pending_merges(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    rows = await ProspectMergeReviewCRUD.list_pending(db)
    return ok(
        [
            {
                "id": r.id,
                "prospect_a_id": r.prospect_a_id,
                "prospect_b_id": r.prospect_b_id,
                "match_score": float(r.match_score),
                "match_reason": r.match_reason,
            }
            for r in rows
        ]
    )


@router.post("/merge-review/{queue_id}/decide")
async def decide_merge(
    queue_id: int,
    payload: MergeDecision,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_admin),
) -> dict:
    """
    Resolve a row in `prospect_merge_review_queue`.

    decision=merged   -> needs (kept_prospect_id, merged_prospect_id);
                         writes prospect_merge_log, soft-deletes loser,
                         marks queue row merged (1).
    decision=rejected -> just marks queue row rejected (2).
    """
    queue_row = await ProspectMergeReviewCRUD.get_by_id(db, queue_id)
    if not queue_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="merge queue row not found")

    if payload.decision == "merged":
        if not (payload.kept_prospect_id and payload.merged_prospect_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="merged requires kept_prospect_id + merged_prospect_id",
            )
        kept = await ProspectCRUD.get_by_id(db, payload.kept_prospect_id)
        loser = await ProspectCRUD.get_by_id(db, payload.merged_prospect_id)
        if not kept or not loser:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
        snapshot = {
            "loser": {
                "id": loser.id,
                "linkedin_url": loser.linkedin_url,
                "email": loser.email,
                "phone": loser.phone,
                "stage": loser.stage,
            }
        }
        # match_strategy = 3 manual_review (§6.14)
        await ProspectMergeLogCRUD.record_merge(
            db,
            kept_prospect_id=kept.id,
            merged_prospect_id=loser.id,
            match_strategy=3,
            merged_by_user_id=user.id,
            snapshot_json=snapshot,
        )
        await ProspectCRUD.soft_delete(db, loser)
        await ProspectMergeReviewCRUD.mark_merged(db, queue_row, reviewed_by_user_id=user.id)
        await AuditLogCRUD.record(
            db,
            actor_user_id=user.id,
            entity_type="prospect",
            entity_id=loser.id,
            action="merged_into",
            after_json={"kept_prospect_id": kept.id},
            ip_address=request.client.host if request.client else None,
        )
        return ok({"queue_id": queue_id, "decision": "merged", "kept_prospect_id": kept.id})

    # rejected
    await ProspectMergeReviewCRUD.mark_rejected(db, queue_row, reviewed_by_user_id=user.id)
    return ok({"queue_id": queue_id, "decision": "rejected"})


@router.get("/{prospect_id}")
async def get_prospect(
    prospect_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """Detail response carries the same `latest_call_*` enrichment as the list."""
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    owner_names = await AdminUserCRUD.names_by_ids(
        db, [prospect.owner_user_id] if prospect.owner_user_id else []
    )
    out = _serialize(prospect, owner_names)
    latest = await CallLogCRUD.latest_per_prospect(db, [prospect.id])
    _attach_latest_call(out, latest.get(prospect.id))
    return ok(out)


@router.get("/{prospect_id}/timeline")
async def get_timeline(
    prospect_id: int,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """
    Unified activity timeline for one prospect (FE Prospect Detail
    "Activity Timeline" tab). Merges, in a single descending feed:

    - `audit_log` rows where `entity_type='prospect'` and `entity_id=<id>`
    - `call_logs` rows where `prospect_id=<id>`
    - `email_replies` rows where `prospect_id=<id>`
    - `landing_page_visits` rows where `prospect_id=<id>`

    Each item carries `{type, ts, ...}` — `type` ∈ {audit, call,
    email_reply, visit}. `ts` is ISO-formatted UTC. `limit` caps the
    merged result (200 default; older entries drop off the bottom).
    """
    from sqlalchemy import select

    from services.audit.models import AuditLog
    from services.call_logs.models import CallLog
    from services.email_replies.models import EmailReply
    from services.landing_pages.models import LandingPageVisit

    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")

    items: list[dict] = []

    # Audit
    audit_stmt = (
        select(AuditLog)
        .where(AuditLog.entity_type == "prospect", AuditLog.entity_id == prospect_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    for row in (await db.execute(audit_stmt)).scalars().all():
        items.append({
            "type": "audit",
            "id": row.id,
            "ts": row.created_at.isoformat() if row.created_at else None,
            "action": row.action,
            "actor_user_id": row.actor_user_id,
            "before_json": row.before_json,
            "after_json": row.after_json,
        })

    # Call logs
    call_stmt = (
        select(CallLog)
        .where(CallLog.prospect_id == prospect_id)
        .order_by(CallLog.called_at.desc())
        .limit(limit)
    )
    for row in (await db.execute(call_stmt)).scalars().all():
        items.append({
            "type": "call",
            "id": row.id,
            "ts": row.called_at.isoformat() if row.called_at else None,
            "outcome": row.outcome,
            "outcome_label": get_outcome_label(CALL_OUTCOMES, row.outcome),
            "callback_at": row.callback_at.isoformat() if row.callback_at else None,
            "notes": row.notes,
            "caller_user_id": row.caller_user_id,
        })

    # Email replies
    reply_stmt = (
        select(EmailReply)
        .where(EmailReply.prospect_id == prospect_id)
        .order_by(EmailReply.received_at.desc())
        .limit(limit)
    )
    for row in (await db.execute(reply_stmt)).scalars().all():
        body = row.raw_body or ""
        snippet = body if len(body) <= 200 else body[:200] + "…"
        items.append({
            "type": "email_reply",
            "id": row.id,
            "ts": row.received_at.isoformat() if row.received_at else None,
            "subject": row.subject,
            "snippet": snippet,
            "classification": row.classification,
            "classification_label": get_reply_label(REPLY_CLASSIFICATIONS, row.classification),
            "classified_by": row.classified_by,
            "classified_by_label": get_reply_label(REPLY_CLASSIFIED_BY, row.classified_by),
            "campaign_id": row.campaign_id,
        })

    # Landing page visits
    visit_stmt = (
        select(LandingPageVisit)
        .where(LandingPageVisit.prospect_id == prospect_id)
        .order_by(LandingPageVisit.visited_at.desc())
        .limit(limit)
    )
    for row in (await db.execute(visit_stmt)).scalars().all():
        items.append({
            "type": "visit",
            "id": row.id,
            "ts": row.visited_at.isoformat() if row.visited_at else None,
            "landing_page_id": row.landing_page_id,
            "utm_source": row.utm_source,
            "utm_medium": row.utm_medium,
            "utm_campaign": row.utm_campaign,
            "referrer": row.referrer,
        })

    # Descending merge — None timestamps last.
    items.sort(key=lambda i: (i["ts"] is None, i["ts"]), reverse=True)
    return ok(items[:limit])


@router.get("/{prospect_id}/stage-history")
async def get_stage_history(
    prospect_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    rows = await ProspectCRUD.list_stage_history(db, prospect_id)
    return ok(
        [
            {
                "id": r.id,
                "from_stage": r.from_stage,
                "from_stage_label": get_label(FUNNEL_STAGES, r.from_stage) if r.from_stage is not None else None,
                "to_stage": r.to_stage,
                "to_stage_label": get_label(FUNNEL_STAGES, r.to_stage),
                "reason": r.reason,
                "changed_by_user_id": r.changed_by_user_id,
                "changed_at": r.changed_at.isoformat() if r.changed_at else None,
            }
            for r in rows
        ]
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_prospect(
    payload: ProspectCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_growth_or_bdr),
) -> dict:
    # Arch-6 dedupe priority: LinkedIn URL > email > phone.
    duplicate = await find_existing(
        db,
        linkedin_url=payload.linkedin_url,
        email=payload.email,
        phone=payload.phone,
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "prospect already exists", "id": duplicate.id},
        )

    prospect = await ProspectCRUD.create(db, **payload.model_dump(exclude_none=True))
    # Arch-22 quality score on insert.
    score = await _quality_for_prospect(db, prospect)
    if score:
        prospect = await ProspectCRUD.set_quality_score(db, prospect, score)
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="prospect",
        entity_id=prospect.id,
        action="create",
        after_json=_audit_payload(prospect),
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(prospect), message="prospect created")


@router.patch("/{prospect_id}")
async def update_prospect(
    prospect_id: int,
    payload: ProspectUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_growth_or_bdr),
) -> dict:
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    before = _audit_payload(prospect)
    prospect = await ProspectCRUD.update(db, prospect, **payload.model_dump(exclude_unset=True))

    # Recompute quality if title/company changed.
    score = await _quality_for_prospect(db, prospect)
    if score and score != prospect.quality_score:
        prospect = await ProspectCRUD.set_quality_score(db, prospect, score)

    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="prospect",
        entity_id=prospect.id,
        action="update",
        before_json=before,
        after_json=_audit_payload(prospect),
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(prospect), message="prospect updated")


@router.post("/{prospect_id}/stage")
async def change_stage(
    prospect_id: int,
    payload: StageChange,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_growth_or_bdr),
) -> dict:
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    prospect = await ProspectCRUD.change_stage(
        db,
        prospect,
        to_stage=payload.to_stage,
        reason=payload.reason,
        changed_by_user_id=user.id,
    )
    return ok(_serialize(prospect), message="stage changed")


@router.post("/{prospect_id}/touch")
async def touch_prospect(
    prospect_id: int,
    payload: TouchRequest,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_growth_or_bdr),
) -> dict:
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    prospect = await ProspectCRUD.record_touch(db, prospect, channel=payload.channel)
    return ok(_serialize(prospect), message="touch recorded")


@router.post("/{prospect_id}/promote-to-thh")
async def promote_to_thh(
    prospect_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_sales),
) -> dict:
    """
    md §9.1 — promote a prospect to a real THH lead.

    - Calls thh-backend's lead-create endpoint via
      `services.integrations.thh_backend.promote_lead`.
    - Sets `prospects.thh_user_id` from the response (Arch-15 manual button).
    - Writes audit_log action=promote_to_thh.
    - Idempotent at the route level: a second call when `thh_user_id` is
      already set returns 409 (UI should disable the button after first call).
    """
    import httpx

    from services.companies.crud import CompanyCRUD
    from services.integrations import thh_backend

    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    if prospect.thh_user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "prospect already promoted", "thh_user_id": prospect.thh_user_id},
        )
    if not prospect.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="prospect has no email — cannot promote",
        )

    company_name = None
    company_domain = None
    if prospect.company_id:
        company = await CompanyCRUD.get_by_id(db, prospect.company_id)
        if company is not None:
            company_name = company.name
            company_domain = company.domain

    try:
        resp = await thh_backend.promote_lead(
            email=prospect.email,
            first_name=prospect.first_name or "",
            last_name=prospect.last_name,
            company_name=company_name,
            domain=company_domain,
            phone=prospect.phone,
            source="lead_engine",
            lead_engine_prospect_id=prospect.id,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"thh-backend promote failed: {exc}",
        )

    thh_user_id = resp.get("users.id") or resp.get("user_id") or resp.get("id")
    if not thh_user_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="thh-backend did not return users.id",
        )
    try:
        thh_user_id = int(thh_user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="thh-backend returned invalid users.id",
        )

    prospect = await ProspectCRUD.set_thh_user_id(db, prospect, thh_user_id)

    # SCHEMA §3: Promote-to-THH must flip stage→converted (also sets
    # converted_at milestone via change_stage).
    if prospect.stage != 2:
        prospect = await ProspectCRUD.change_stage(
            db,
            prospect,
            to_stage=2,  # §6.2 converted
            reason="promote_to_thh",
            changed_by_user_id=user.id,
        )

    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="prospect",
        entity_id=prospect.id,
        action="promote_to_thh",
        after_json={"thh_user_id": thh_user_id},
        ip_address=request.client.host if request.client else None,
    )

    return ok(
        {**_serialize(prospect), "thh_user_id": thh_user_id},
        message="promoted to THH",
    )


@router.delete("/{prospect_id}")
async def delete_prospect(
    prospect_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_admin),
) -> dict:
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    await ProspectCRUD.soft_delete(db, prospect)
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="prospect",
        entity_id=prospect.id,
        action="delete",
        ip_address=request.client.host if request.client else None,
    )
    return ok(message="prospect deleted")
