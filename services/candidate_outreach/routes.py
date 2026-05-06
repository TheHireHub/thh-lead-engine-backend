"""
FastAPI routes for candidate_outreach (proposed §9.6).

Three audiences:
1. **HH-BE webhook** (`X-Service-Token`) — POST a new outreach event.
2. **Admin UI reads** (cookie auth, dashboard_read role-set) — list +
   detail endpoints powering the Outreach Activity panel.
3. **Admin UI writes** (cookie auth, sales/csm/admin) — flip status,
   record per-candidate outcome, soft-delete.

The webhook returns 200 on idempotent re-receive (HH-BE retries collapse
to one row); the body's `created` flag tells HH-BE if the row was new.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.deps import (
    require_admin,
    require_dashboard_read,
    require_sales_or_csm,
)
from services.admin_users.models import AdminUser
from services.common.envelope import ok

from .auth import require_service_token
from .crud import CandidateOutreachCRUD
from .enums import (
    CANDIDATE_OUTCOMES,
    OUTREACH_CHANNELS,
    OUTREACH_STATUSES,
    get_label,
)
from .schemas import (
    IngestPayload,
    OutcomeUpdate,
    OutreachCandidateOut,
    OutreachOut,
    OutreachWithCandidatesOut,
    StatusUpdate,
)

router = APIRouter(prefix="/api/candidate-outreach", tags=["candidate_outreach"])


# ─── Serialisers ────────────────────────────────────────────────────────


def _serialize_outreach(o) -> dict:
    out = OutreachOut.model_validate(o).model_dump()
    out["channel_label"] = get_label(OUTREACH_CHANNELS, o.channel)
    out["status_label"] = get_label(OUTREACH_STATUSES, o.status)
    return out


def _serialize_candidate(c) -> dict:
    out = OutreachCandidateOut.model_validate(c).model_dump()
    out["outcome_label"] = (
        get_label(CANDIDATE_OUTCOMES, c.outcome) if c.outcome is not None else None
    )
    return out


# ─── Inbound webhook (THH → LEADS, X-Service-Token) ─────────────────────


@router.post("/ingest", status_code=status.HTTP_200_OK)
async def ingest_outreach(
    payload: IngestPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_service_token),
) -> dict:
    """
    HH-BE pushes one click here. Idempotent on `dedup_key` — retries
    return 200 with `created=False`.
    """
    outreach, created = await CandidateOutreachCRUD.ingest(
        db,
        payload,
        ip_address=request.client.host if request.client else None,
    )
    return ok(
        {
            "id": outreach.id,
            "created": created,
            "prospect_id": outreach.prospect_id,
            "candidate_count": outreach.candidate_count,
        },
        message="ingested" if created else "already_exists",
    )


# ─── Reads (cookie auth) ────────────────────────────────────────────────


@router.get("/by-prospect/{prospect_id}")
async def list_for_prospect(
    prospect_id: int,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """List outreach events for a single prospect (Outreach Activity panel)."""
    rows = await CandidateOutreachCRUD.list_for_prospect(
        db, prospect_id, limit=limit, offset=offset
    )
    return ok([_serialize_outreach(r) for r in rows])


@router.get("/recent")
async def list_recent(
    status_filter: Optional[int] = None,
    unattributed_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """Cross-prospect feed for the standalone Outreach board."""
    rows = await CandidateOutreachCRUD.list_recent(
        db,
        status=status_filter,
        unattributed_only=unattributed_only,
        limit=limit,
        offset=offset,
    )
    return ok([_serialize_outreach(r) for r in rows])


@router.get("/{outreach_id}")
async def get_one(
    outreach_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """Detail with all per-candidate child rows."""
    outreach = await CandidateOutreachCRUD.get_by_id(db, outreach_id)
    if outreach is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    candidates = await CandidateOutreachCRUD.list_candidates(db, outreach_id)
    payload = _serialize_outreach(outreach)
    payload["candidates"] = [_serialize_candidate(c) for c in candidates]
    return ok(payload)


# ─── Mutations (cookie auth, sales/csm/admin) ───────────────────────────


@router.patch("/{outreach_id}/status")
async def patch_status(
    outreach_id: int,
    body: StatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_sales_or_csm),
) -> dict:
    """Flip outreach status (Mark Engaged / Hired / Dropped)."""
    outreach = await CandidateOutreachCRUD.get_by_id(db, outreach_id)
    if outreach is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if outreach.status == 2 and body.status != 2:
        # One-way ratchet: hired is terminal positive; refuse downgrade.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="outreach is hired; status cannot be reverted",
        )
    updated = await CandidateOutreachCRUD.update_status(
        db,
        outreach,
        new_status=body.status,
        actor_user_id=user.id,
        notes=body.notes,
    )
    return ok(_serialize_outreach(updated))


@router.patch("/candidates/{candidate_row_id}/outcome")
async def patch_candidate_outcome(
    candidate_row_id: int,
    body: OutcomeUpdate,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_sales_or_csm),
) -> dict:
    """Record a per-candidate outcome inside an outreach event."""
    candidate = await CandidateOutreachCRUD.get_candidate_by_id(db, candidate_row_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    updated = await CandidateOutreachCRUD.update_candidate_outcome(
        db, candidate, new_outcome=body.outcome, actor_user_id=user.id
    )
    return ok(_serialize_candidate(updated))


@router.delete("/{outreach_id}", status_code=status.HTTP_200_OK)
async def soft_delete(
    outreach_id: int,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_admin),
) -> dict:
    """Admin-only soft delete (Arch-19)."""
    outreach = await CandidateOutreachCRUD.get_by_id(db, outreach_id)
    if outreach is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    await CandidateOutreachCRUD.soft_delete(db, outreach, actor_user_id=user.id)
    return ok({"id": outreach_id, "deleted": True})
