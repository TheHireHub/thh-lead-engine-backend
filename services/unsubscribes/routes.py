"""FastAPI routes for unsubscribes (Schema doc §7.14, Arch-26 compliance)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.deps import require_internal
from services.admin_users.models import AdminUser
from services.audit.crud import AuditLogCRUD
from services.campaigns.crud import CampaignEventCRUD
from services.common.envelope import ok
from services.prospects.crud import ProspectCRUD

from .crud import UnsubscribeCRUD
from .schemas import UnsubscribeCreate, UnsubscribeOut
from .tokens import verify_token

router = APIRouter(prefix="/api/unsubscribes", tags=["unsubscribes"])

_STAGE_UNSUBSCRIBED = 4   # §6.2
_EVENT_UNSUBSCRIBED = 7   # §6.7


async def _process_unsubscribe(
    db: AsyncSession,
    *,
    email: str,
    request: Request,
    prospect_id: int | None = None,
    source_campaign_id: int | None = None,
    reason: str | None = None,
):
    row, created = await UnsubscribeCRUD.get_or_create(
        db,
        email=email,
        prospect_id=prospect_id,
        source_campaign_id=source_campaign_id,
        reason=reason,
    )

    if created:
        prospect = None
        if prospect_id:
            prospect = await ProspectCRUD.get_by_id(db, prospect_id)
        if prospect is None:
            prospect = await ProspectCRUD.get_by_email(db, email)

        if prospect is not None and prospect.stage != _STAGE_UNSUBSCRIBED:
            await ProspectCRUD.change_stage(
                db,
                prospect,
                to_stage=_STAGE_UNSUBSCRIBED,
                reason=reason or "unsubscribe_link",
            )
            if row.prospect_id is None:
                row.prospect_id = prospect.id
                await db.commit()
                await db.refresh(row)

        if source_campaign_id and prospect is not None:
            await CampaignEventCRUD.record(
                db,
                campaign_id=source_campaign_id,
                prospect_id=prospect.id,
                event_type=_EVENT_UNSUBSCRIBED,
                payload_json={"unsubscribe_id": row.id},
            )

        await AuditLogCRUD.record(
            db,
            actor_user_id=None,  # public unsubscribe — no actor
            entity_type="unsubscribe",
            entity_id=row.id,
            action="create",
            after_json={
                "email": row.email,
                "prospect_id": row.prospect_id,
                "source_campaign_id": row.source_campaign_id,
            },
            ip_address=request.client.host if request.client else None,
        )

    return row, created


@router.post("/", status_code=status.HTTP_201_CREATED)
async def unsubscribe(
    payload: UnsubscribeCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Public endpoint — invoked by the email unsubscribe link or by the admin
    UI. Idempotent.
    """
    row, created = await _process_unsubscribe(
        db,
        email=payload.email,
        request=request,
        prospect_id=payload.prospect_id,
        source_campaign_id=payload.source_campaign_id,
        reason=payload.reason,
    )
    body = UnsubscribeOut.model_validate(row).model_dump(mode="json")
    return ok(body, message=("unsubscribed" if created else "already unsubscribed"))


@router.post("/by-token/{token}")
async def unsubscribe_by_token(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Public endpoint — invoked by the one-click unsubscribe link in
    outbound emails. Token = HMAC of email + secret per Arch-26.
    """
    email = verify_token(token)
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid token")
    row, created = await _process_unsubscribe(
        db,
        email=email,
        request=request,
        reason="unsubscribe_token",
    )
    body = UnsubscribeOut.model_validate(row).model_dump(mode="json")
    return ok(body, message=("unsubscribed" if created else "already unsubscribed"))


@router.get("/")
async def list_unsubscribes(
    source_campaign_id: int | None = None,
    limit: int = 200,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    rows = await UnsubscribeCRUD.list_recent(
        db, source_campaign_id=source_campaign_id, limit=limit, offset=offset
    )
    return ok([UnsubscribeOut.model_validate(r).model_dump(mode="json") for r in rows])


@router.get("/check/{email}")
async def check(
    email: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    return ok({"unsubscribed": await UnsubscribeCRUD.is_unsubscribed(db, email)})
