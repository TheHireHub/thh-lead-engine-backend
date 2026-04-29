"""FastAPI routes for unsubscribes (Schema doc §7.14, Arch-26 compliance)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.audit.crud import AuditLogCRUD
from services.campaigns.crud import CampaignEventCRUD
from services.common.envelope import ok
from services.prospects.crud import ProspectCRUD

from .crud import UnsubscribeCRUD
from .schemas import UnsubscribeCreate, UnsubscribeOut

router = APIRouter(prefix="/api/unsubscribes", tags=["unsubscribes"])

# §6.2 funnel stage int
_STAGE_UNSUBSCRIBED = 4
# §6.7 campaign event type
_EVENT_UNSUBSCRIBED = 7


@router.post("/", status_code=status.HTTP_201_CREATED)
async def unsubscribe(
    payload: UnsubscribeCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Public endpoint — invoked from the unsubscribe link in outbound emails
    (Apollo). Idempotent: re-submitting the same email returns the existing
    row.

    Side-effects:
    - Resolve prospect by `prospect_id` or by email; if found, move
      `prospects.stage` to 4 (unsubscribed) via change_stage (Arch-18 audit
      + §7.5 stage history written automatically).
    - If `source_campaign_id` given, write campaign_event(7=unsubscribed).
    - Always write audit_log row.
    """
    row, created = await UnsubscribeCRUD.get_or_create(
        db,
        email=payload.email,
        prospect_id=payload.prospect_id,
        source_campaign_id=payload.source_campaign_id,
        reason=payload.reason,
    )

    if created:
        # Find prospect (by id if given, else by email).
        prospect = None
        if payload.prospect_id:
            prospect = await ProspectCRUD.get_by_id(db, payload.prospect_id)
        if prospect is None:
            prospect = await ProspectCRUD.get_by_email(db, payload.email)

        if prospect is not None and prospect.stage != _STAGE_UNSUBSCRIBED:
            await ProspectCRUD.change_stage(
                db,
                prospect,
                to_stage=_STAGE_UNSUBSCRIBED,
                reason=payload.reason or "unsubscribe_link",
            )
            # Backfill prospect_id on the unsubscribe row if it was missing.
            if row.prospect_id is None:
                row.prospect_id = prospect.id
                await db.commit()
                await db.refresh(row)

        if payload.source_campaign_id and prospect is not None:
            await CampaignEventCRUD.record(
                db,
                campaign_id=payload.source_campaign_id,
                prospect_id=prospect.id,
                event_type=_EVENT_UNSUBSCRIBED,
                payload_json={"unsubscribe_id": row.id},
            )

        await AuditLogCRUD.record(
            db,
            actor_user_id=None,  # public endpoint, no actor
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

    body = UnsubscribeOut.model_validate(row).model_dump(mode="json")
    return ok(body, message=("unsubscribed" if created else "already unsubscribed"))


@router.get("/")
async def list_unsubscribes(
    source_campaign_id: int | None = None,
    limit: int = 200,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = await UnsubscribeCRUD.list_recent(
        db, source_campaign_id=source_campaign_id, limit=limit, offset=offset
    )
    return ok([UnsubscribeOut.model_validate(r).model_dump(mode="json") for r in rows])


@router.get("/check/{email}")
async def check(email: str, db: AsyncSession = Depends(get_db)) -> dict:
    return ok({"unsubscribed": await UnsubscribeCRUD.is_unsubscribed(db, email)})
