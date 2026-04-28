"""FastAPI routes for inbound webhooks (Calendly, Apollo, email provider)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.common.envelope import ok

from .crud import WebhookDeliveryCRUD

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/calendly")
async def calendly_webhook(
    request: Request,
    calendly_signature: str | None = Header(default=None, alias="Calendly-Webhook-Signature"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    TODO:
    1. Verify HMAC-SHA256 signature against `CALENDLY_WEBHOOK_SIGNING_KEY` env.
    2. Check timestamp tolerance (WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS).
    3. Extract external_event_id from payload.
    4. Idempotency: WebhookDeliveryCRUD.record() — duplicate => return 200 + {duplicate:true}.
    5. Enqueue ARQ task to process (set demo_booked_at on prospect, write campaign_event=8).
    """
    payload = await request.json()
    external_id = str(payload.get("event", {}).get("uri", "unknown"))
    row, dup = await WebhookDeliveryCRUD.record(
        db, provider=0, external_event_id=external_id,
        payload_json=payload, signature=calendly_signature,
    )
    if dup:
        return ok({"duplicate": True, "id": row.id})
    return ok({"duplicate": False, "id": row.id}, message="webhook received")


@router.post("/apollo")
async def apollo_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """TODO: same pattern as Calendly. Provider=1."""
    payload = await request.json()
    external_id = str(payload.get("id", "unknown"))
    row, dup = await WebhookDeliveryCRUD.record(
        db, provider=1, external_event_id=external_id, payload_json=payload,
    )
    return ok({"duplicate": dup, "id": row.id})
