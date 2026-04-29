"""FastAPI routes for prospects (Schema doc §7.3-§7.5, §7.19-§7.20, Arch-6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.deps import (
    require_admin,
    require_growth_or_bdr,
    require_internal,
    require_sales,
)
from services.admin_users.models import AdminUser
from services.audit.crud import AuditLogCRUD
from services.common.envelope import ok

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


def _serialize(p) -> dict:
    out = ProspectOut.model_validate(p).model_dump(mode="json")
    out["stage_label"] = get_label(FUNNEL_STAGES, p.stage)
    out["source_channel_label"] = get_label(CHANNELS, p.source_channel)
    return out


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


@router.get("/")
async def list_prospects(
    stage: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    prospects = await ProspectCRUD.list_by_stage(db, stage=stage, limit=limit, offset=offset)
    return ok([_serialize(p) for p in prospects])


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
    _user: AdminUser = Depends(require_internal),
) -> dict:
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    return ok(_serialize(prospect))


@router.get("/{prospect_id}/stage-history")
async def get_stage_history(
    prospect_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
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


@router.post("/", status_code=status.HTTP_201_CREATED)
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
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_sales),
) -> dict:
    """Phase 3 stub. Real implementation calls thh-backend §9.1."""
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="TODO Phase 3 — promote-to-thh integration with thh-backend",
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
