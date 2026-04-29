"""FastAPI routes for email_replies (Schema doc §7.13, §6.8, §6.9, Arch-11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.deps import (
    require_growth_or_bdr,
    require_internal,
)
from services.admin_users.models import AdminUser
from services.audit.crud import AuditLogCRUD
from services.campaigns.crud import CampaignEventCRUD
from services.common.envelope import ok
from services.prospects.crud import ProspectCRUD

from .crud import EmailReplyCRUD
from .enums import REPLY_CLASSIFICATIONS, REPLY_CLASSIFIED_BY, get_label
from .schemas import EmailReplyCreate, EmailReplyOut, EmailReplyReclassify

router = APIRouter(prefix="/api/email-replies", tags=["email_replies"])

# §6.8
_CLASSIFICATION_POSITIVE = 0
_CLASSIFICATION_NEGATIVE = 1

# §6.7 event types
_EVENT_REPLIED_POSITIVE = 5
_EVENT_REPLIED_NEGATIVE = 6


def _serialize(r) -> dict:
    out = EmailReplyOut.model_validate(r).model_dump(mode="json")
    out["classification_label"] = get_label(REPLY_CLASSIFICATIONS, r.classification)
    out["classified_by_label"] = get_label(REPLY_CLASSIFIED_BY, r.classified_by)
    return out


async def _propagate_reply_side_effects(db: AsyncSession, reply) -> None:
    """heat + campaign_event side-effects per §6.7 + Arch-21."""
    prospect = await ProspectCRUD.get_by_id(db, reply.prospect_id)
    if prospect is None:
        return

    if reply.classification == _CLASSIFICATION_POSITIVE:
        await ProspectCRUD.apply_heat_event(db, prospect, event_type="positive_reply")
        await CampaignEventCRUD.record(
            db,
            campaign_id=reply.campaign_id,
            prospect_id=reply.prospect_id,
            event_type=_EVENT_REPLIED_POSITIVE,
            payload_json={"reply_id": reply.id},
        )
    elif reply.classification == _CLASSIFICATION_NEGATIVE:
        await CampaignEventCRUD.record(
            db,
            campaign_id=reply.campaign_id,
            prospect_id=reply.prospect_id,
            event_type=_EVENT_REPLIED_NEGATIVE,
            payload_json={"reply_id": reply.id},
        )


@router.get("/")
async def list_replies(
    classification: int | None = None,
    limit: int = 200,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    rows = await EmailReplyCRUD.list_recent(
        db, classification=classification, limit=limit, offset=offset
    )
    return ok([_serialize(r) for r in rows])


@router.get("/needs-review")
async def list_needs_review(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    rows = await EmailReplyCRUD.list_needs_review(db, limit=limit, offset=offset)
    return ok([_serialize(r) for r in rows])


@router.get("/by-prospect/{prospect_id}")
async def list_for_prospect(
    prospect_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    rows = await EmailReplyCRUD.list_for_prospect(db, prospect_id)
    return ok([_serialize(r) for r in rows])


@router.get("/{reply_id}")
async def get_reply(
    reply_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    reply = await EmailReplyCRUD.get_by_id(db, reply_id)
    if not reply:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="reply not found")
    return ok(_serialize(reply))


@router.post("/", status_code=status.HTTP_201_CREATED)
async def record_reply(
    payload: EmailReplyCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_growth_or_bdr),
) -> dict:
    reply = await EmailReplyCRUD.create(db, **payload.model_dump(exclude_unset=True))
    await _propagate_reply_side_effects(db, reply)
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="email_reply",
        entity_id=reply.id,
        action="create",
        after_json={
            "prospect_id": reply.prospect_id,
            "classification": reply.classification,
            "classified_by": reply.classified_by,
        },
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(reply), message="reply recorded")


@router.post("/{reply_id}/reclassify")
async def reclassify(
    reply_id: int,
    payload: EmailReplyReclassify,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_growth_or_bdr),
) -> dict:
    reply = await EmailReplyCRUD.get_by_id(db, reply_id)
    if not reply:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="reply not found")
    before = {"classification": reply.classification, "classified_by": reply.classified_by}
    reply = await EmailReplyCRUD.reclassify(db, reply, classification=payload.classification)
    await _propagate_reply_side_effects(db, reply)
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="email_reply",
        entity_id=reply.id,
        action="reclassify",
        before_json=before,
        after_json={"classification": reply.classification, "classified_by": reply.classified_by},
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(reply), message="reclassified")
