"""FastAPI routes for prospects (Schema doc §7.3-§7.5, §7.19-§7.20)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.common.envelope import ok

from .crud import ProspectCRUD, ProspectMergeReviewCRUD
from .enums import CHANNELS, FUNNEL_STAGES, get_label
from .schemas import ProspectCreate, ProspectOut, ProspectUpdate, StageChange

router = APIRouter(prefix="/api/prospects", tags=["prospects"])


def _serialize(p) -> dict:
    out = ProspectOut.model_validate(p).model_dump()
    out["stage_label"] = get_label(FUNNEL_STAGES, p.stage)
    out["source_channel_label"] = get_label(CHANNELS, p.source_channel)
    return out


@router.get("/")
async def list_prospects(
    stage: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> dict:
    prospects = await ProspectCRUD.list_by_stage(db, stage=stage, limit=limit, offset=offset)
    return ok([_serialize(p) for p in prospects])


@router.get("/{prospect_id}")
async def get_prospect(prospect_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    return ok(_serialize(prospect))


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_prospect(payload: ProspectCreate, db: AsyncSession = Depends(get_db)) -> dict:
    # Dedupe priority: LinkedIn URL > email > phone (Arch-6)
    if payload.linkedin_url:
        existing = await ProspectCRUD.get_by_linkedin(db, payload.linkedin_url)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="prospect with this LinkedIn URL exists")
    prospect = await ProspectCRUD.create(db, **payload.model_dump(exclude_none=True))
    return ok(_serialize(prospect), message="prospect created")


@router.patch("/{prospect_id}")
async def update_prospect(
    prospect_id: int, payload: ProspectUpdate, db: AsyncSession = Depends(get_db)
) -> dict:
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    prospect = await ProspectCRUD.update(db, prospect, **payload.model_dump(exclude_unset=True))
    return ok(_serialize(prospect), message="prospect updated")


@router.post("/{prospect_id}/stage")
async def change_stage(
    prospect_id: int, payload: StageChange, db: AsyncSession = Depends(get_db)
) -> dict:
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    prospect = await ProspectCRUD.change_stage(
        db, prospect, to_stage=payload.to_stage, reason=payload.reason
    )
    return ok(_serialize(prospect), message="stage changed")


@router.delete("/{prospect_id}")
async def delete_prospect(prospect_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    prospect = await ProspectCRUD.get_by_id(db, prospect_id)
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospect not found")
    await ProspectCRUD.soft_delete(db, prospect)
    return ok(message="prospect deleted")


@router.get("/merge-review/pending")
async def list_pending_merges(db: AsyncSession = Depends(get_db)) -> dict:
    rows = await ProspectMergeReviewCRUD.list_pending(db)
    return ok([{"id": r.id, "prospect_a_id": r.prospect_a_id, "prospect_b_id": r.prospect_b_id,
                "match_score": float(r.match_score), "match_reason": r.match_reason} for r in rows])
