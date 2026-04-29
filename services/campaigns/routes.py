"""FastAPI routes for campaigns + events (Schema doc §7.6-§7.8, §6.5-§6.7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.deps import (
    require_admin,
    require_dashboard_read,
    require_growth,
)
from services.admin_users.models import AdminUser
from services.audit.crud import AuditLogCRUD
from services.common.envelope import ok
from services.prospects.crud import ProspectCRUD

from .crud import CampaignCRUD, CampaignEventCRUD, CampaignProspectCRUD
from .enums import (
    CAMPAIGN_EVENT_TYPES,
    CAMPAIGN_STATUSES,
    CHANNELS,
    get_label,
)
from .schemas import (
    CampaignAddProspects,
    CampaignCreate,
    CampaignEventCreate,
    CampaignOut,
    CampaignStatusChange,
    CampaignUpdate,
)

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


# Event types (§6.7) that mutate prospect state.
_EVENT_HEAT_KEY = {
    2: "open",
    3: "click",
    5: "positive_reply",
    12: "visit_no_signup",
}
_EVENT_UNSUBSCRIBED = 7
_EVENT_DEMO_BOOKED = 8
_STAGE_UNSUBSCRIBED = 4  # §6.2


def _serialize(c) -> dict:
    out = CampaignOut.model_validate(c).model_dump(mode="json")
    out["channel_label"] = get_label(CHANNELS, c.channel)
    out["status_label"] = get_label(CAMPAIGN_STATUSES, c.status)
    return out


def _audit_payload(c) -> dict:
    return {"name": c.name, "channel": c.channel, "status": c.status}


@router.get("/")
async def list_campaigns(
    status: int | None = None,
    channel: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    rows = await CampaignCRUD.list_all(
        db, status=status, channel=channel, limit=limit, offset=offset
    )
    return ok([_serialize(c) for c in rows])


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    campaign = await CampaignCRUD.get_by_id(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="campaign not found")
    return ok(_serialize(campaign))


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_growth),
) -> dict:
    campaign = await CampaignCRUD.create(
        db,
        **payload.model_dump(exclude_none=True),
        created_by_user_id=user.id,
    )
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="campaign",
        entity_id=campaign.id,
        action="create",
        after_json=_audit_payload(campaign),
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(campaign), message="campaign created")


@router.patch("/{campaign_id}")
async def update_campaign(
    campaign_id: int,
    payload: CampaignUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_growth),
) -> dict:
    campaign = await CampaignCRUD.get_by_id(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="campaign not found")
    before = _audit_payload(campaign)
    campaign = await CampaignCRUD.update(db, campaign, **payload.model_dump(exclude_unset=True))
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="campaign",
        entity_id=campaign.id,
        action="update",
        before_json=before,
        after_json=_audit_payload(campaign),
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(campaign), message="campaign updated")


@router.post("/{campaign_id}/status")
async def change_campaign_status(
    campaign_id: int,
    payload: CampaignStatusChange,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_growth),
) -> dict:
    campaign = await CampaignCRUD.get_by_id(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="campaign not found")
    before_status = campaign.status
    campaign = await CampaignCRUD.change_status(db, campaign, status=payload.status)
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="campaign",
        entity_id=campaign.id,
        action="status_change",
        before_json={"status": before_status},
        after_json={"status": campaign.status},
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(campaign), message="campaign status changed")


@router.delete("/{campaign_id}")
async def delete_campaign(
    campaign_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_admin),
) -> dict:
    campaign = await CampaignCRUD.get_by_id(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="campaign not found")
    await CampaignCRUD.soft_delete(db, campaign)
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="campaign",
        entity_id=campaign.id,
        action="delete",
        ip_address=request.client.host if request.client else None,
    )
    return ok(message="campaign deleted")


@router.post("/{campaign_id}/prospects", status_code=status.HTTP_201_CREATED)
async def add_prospects(
    campaign_id: int,
    payload: CampaignAddProspects,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_growth),
) -> dict:
    campaign = await CampaignCRUD.get_by_id(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="campaign not found")
    added, skipped = await CampaignProspectCRUD.add_prospects(
        db, campaign_id=campaign_id, prospect_ids=payload.prospect_ids
    )
    return ok({"added": added, "skipped": skipped}, message="prospects added")


@router.get("/{campaign_id}/prospects")
async def list_campaign_prospects(
    campaign_id: int,
    status: int | None = None,
    limit: int = 500,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    rows = await CampaignProspectCRUD.list_for_campaign(
        db, campaign_id, status=status, limit=limit, offset=offset
    )
    out = []
    for r in rows:
        events = await CampaignEventCRUD.list_for_prospect(db, r.prospect_id, limit=1)
        latest = events[0] if events else None
        out.append(
            {
                "campaign_id": r.campaign_id,
                "prospect_id": r.prospect_id,
                "status": r.status,
                "added_at": r.added_at.isoformat() if r.added_at else None,
                "latest_event": (
                    {
                        "event_type": latest.event_type,
                        "event_type_label": get_label(CAMPAIGN_EVENT_TYPES, latest.event_type),
                        "occurred_at": latest.occurred_at.isoformat() if latest.occurred_at else None,
                    }
                    if latest
                    else None
                ),
            }
        )
    return ok(out)


@router.get("/{campaign_id}/events")
async def list_campaign_events(
    campaign_id: int,
    event_type: int | None = None,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    rows = await CampaignEventCRUD.list_for_campaign(
        db, campaign_id, event_type=event_type, limit=limit
    )
    return ok(
        [
            {
                "id": r.id,
                "campaign_id": r.campaign_id,
                "prospect_id": r.prospect_id,
                "event_type": r.event_type,
                "event_type_label": get_label(CAMPAIGN_EVENT_TYPES, r.event_type),
                "payload_json": r.payload_json,
                "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
            }
            for r in rows
        ]
    )


@router.get("/{campaign_id}/funnel")
async def campaign_funnel(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """Aggregate counts by event_type — feeds the campaign funnel viz."""
    counts = await CampaignEventCRUD.count_by_event_type(db, campaign_id)
    return ok(
        {
            str(et): {"count": n, "label": get_label(CAMPAIGN_EVENT_TYPES, et)}
            for et, n in counts.items()
        }
    )


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def record_event(
    payload: CampaignEventCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_growth),
) -> dict:
    """
    Record a campaign event. Side-effects on prospect state per §6.7 + Arch-21.
    """
    event = await CampaignEventCRUD.record(db, **payload.model_dump(exclude_none=True))

    prospect = await ProspectCRUD.get_by_id(db, payload.prospect_id)
    if prospect is not None:
        heat_key = _EVENT_HEAT_KEY.get(payload.event_type)
        if heat_key:
            await ProspectCRUD.apply_heat_event(db, prospect, event_type=heat_key)
        if payload.event_type == _EVENT_DEMO_BOOKED:
            await ProspectCRUD.set_demo_booked(db, prospect)
        elif payload.event_type == _EVENT_UNSUBSCRIBED:
            await ProspectCRUD.change_stage(
                db,
                prospect,
                to_stage=_STAGE_UNSUBSCRIBED,
                reason="campaign_event:unsubscribed",
                changed_by_user_id=user.id,
            )

    return ok({"id": event.id}, message="event recorded")
