"""FastAPI routes for prospects (Schema doc §7.3-§7.5, §7.19-§7.20, Arch-6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.audit.crud import AuditLogCRUD
from services.common.envelope import ok

from .crud import ProspectCRUD, ProspectMergeReviewCRUD
from .enums import CHANNELS, FUNNEL_STAGES, get_label
from .schemas import ProspectCreate, ProspectOut, ProspectUpdate, StageChange

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


@router.get("/")
async def list_prospects(
    stage: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> dict:
    prospects = await ProspectCRUD.list_by_stage(db, stage=stage, limit=limit, offset=offset)
    return ok([_serialize(p) for p in prospects])


@router.get("/merge-review/pending")
async def list_pending_merges(db: AsyncSession = Depends(get_db)) -> dict:
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


@router.get("/{prospect_id}")
async def get_prospect(prospect_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    return ok(_serialize(prospect))


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_prospect(
    payload: ProspectCreate,
    request: Request,
    actor_user_id: int | None = None,  # TODO replace with Depends(get_current_user) in auth-sweep
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Arch-6 dedupe priority: LinkedIn URL > email > phone.
    duplicate = await ProspectCRUD.find_duplicate(
        db,
        linkedin_url=payload.linkedin_url,
        email=payload.email,
        phone=payload.phone,
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"prospect already exists (id={duplicate.id})",
        )

    prospect = await ProspectCRUD.create(db, **payload.model_dump(exclude_none=True))
    await AuditLogCRUD.record(
        db,
        actor_user_id=actor_user_id,
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
    actor_user_id: int | None = None,  # TODO replace with Depends(get_current_user) in auth-sweep
    db: AsyncSession = Depends(get_db),
) -> dict:
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    before = _audit_payload(prospect)
    prospect = await ProspectCRUD.update(db, prospect, **payload.model_dump(exclude_unset=True))
    await AuditLogCRUD.record(
        db,
        actor_user_id=actor_user_id,
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
    actor_user_id: int | None = None,  # TODO replace with Depends(get_current_user) in auth-sweep
    db: AsyncSession = Depends(get_db),
) -> dict:
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    prospect = await ProspectCRUD.change_stage(
        db,
        prospect,
        to_stage=payload.to_stage,
        reason=payload.reason,
        changed_by_user_id=actor_user_id,
    )
    return ok(_serialize(prospect), message="stage changed")


@router.delete("/{prospect_id}")
async def delete_prospect(
    prospect_id: int,
    request: Request,
    actor_user_id: int | None = None,  # TODO replace with Depends(get_current_user) in auth-sweep
    db: AsyncSession = Depends(get_db),
) -> dict:
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    await ProspectCRUD.soft_delete(db, prospect)
    await AuditLogCRUD.record(
        db,
        actor_user_id=actor_user_id,
        entity_type="prospect",
        entity_id=prospect.id,
        action="delete",
        ip_address=request.client.host if request.client else None,
    )
    return ok(message="prospect deleted")
