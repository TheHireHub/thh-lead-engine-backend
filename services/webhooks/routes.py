"""FastAPI routes for inbound webhooks (Schema doc §7.18, Arch-13, Arch-14)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.audit.crud import AuditLogCRUD
from services.campaigns.crud import CampaignEventCRUD
from services.common.envelope import fail, ok
from services.prospects.crud import ProspectCRUD

from .crud import WebhookDeliveryCRUD

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)

# §6.12 webhook providers
_PROVIDER_CALENDLY = 0
_PROVIDER_APOLLO = 1
# §6.7 campaign event types
_EVENT_DEMO_BOOKED = 8
_EVENT_DEMO_NO_SHOW = 10


def _verify_calendly_signature(body: bytes, header: str | None) -> bool:
    """
    Verify Calendly's `Calendly-Webhook-Signature` header per Arch-14.

    Header format: `t=<unix_timestamp>,v1=<hex_hmac_sha256>`. The signed
    payload is `t + "." + raw_body`. 5-minute timestamp window per Arch-14
    (env override `WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS`).

    Returns False if signing key not configured (dev), header malformed,
    timestamp outside window, or signature mismatch.
    """
    secret = os.getenv("CALENDLY_WEBHOOK_SIGNING_KEY")
    if not secret or not header:
        return False
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    ts = parts.get("t")
    sig = parts.get("v1")
    if not ts or not sig:
        return False
    try:
        ts_int = int(ts)
    except ValueError:
        return False
    tolerance = int(os.getenv("WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS", "300"))
    if abs(time.time() - ts_int) > tolerance:
        return False
    signed = f"{ts}.".encode("utf-8") + body
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


@router.post("/calendly")
async def calendly_webhook(
    request: Request,
    calendly_signature: str | None = Header(default=None, alias="Calendly-Webhook-Signature"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Calendly webhook (Arch-13). Closes the postMessage gap — sets
    `prospects.demo_booked_at` reliably even if the browser closed before
    the success page rendered.

    Pipeline:
    1. Read raw body for HMAC verification (Arch-14).
    2. Verify signature + 5-min timestamp window. Fail = 401.
    3. Parse JSON. Extract Calendly event URI as external_event_id.
    4. Idempotency via webhook_deliveries (UNIQUE on provider+event_id).
    5. On `invitee.created`: resolve prospect by email, call
       `ProspectCRUD.set_demo_booked` (idempotent), write
       `campaign_event(event_type=8 demo_booked)`, audit.
    6. Mark webhook delivery processed (or failed on exception).
    """
    raw_body = await request.body()

    # 1+2. Signature check. Skip enforcement only if no key configured (dev).
    if os.getenv("CALENDLY_WEBHOOK_SIGNING_KEY"):
        if not _verify_calendly_signature(raw_body, calendly_signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature"
            )

    # 3. Parse payload.
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json")

    event = (payload or {}).get("event") or {}
    event_type = (payload or {}).get("event_type") or payload.get("event")  # Calendly variants
    if isinstance(event_type, dict):
        event_type = event_type.get("kind") or event_type.get("uri")
    payload_obj = (payload or {}).get("payload") or {}
    external_id = (
        (payload or {}).get("uri")
        or payload_obj.get("uri")
        or event.get("uri")
        or "unknown"
    )

    # 4. Idempotency.
    delivery, is_duplicate = await WebhookDeliveryCRUD.record(
        db,
        provider=_PROVIDER_CALENDLY,
        external_event_id=str(external_id),
        payload_json=payload,
        signature=calendly_signature,
    )
    if is_duplicate:
        return ok({"duplicate": True, "id": delivery.id})

    # 5. Process invitee.created / invitee.canceled.
    try:
        invitee_email = (
            payload_obj.get("email")
            or (payload_obj.get("invitee") or {}).get("email")
        )
        kind = str(event_type or "").lower()

        if "invitee.created" in kind and invitee_email:
            prospect = await ProspectCRUD.get_by_email(db, invitee_email)
            if prospect is not None:
                await ProspectCRUD.set_demo_booked(db, prospect)
                await CampaignEventCRUD.record(
                    db,
                    campaign_id=None,
                    prospect_id=prospect.id,
                    event_type=_EVENT_DEMO_BOOKED,
                    payload_json={"calendly_event_uri": external_id},
                )
                await AuditLogCRUD.record(
                    db,
                    actor_user_id=None,
                    entity_type="prospect",
                    entity_id=prospect.id,
                    action="calendly_demo_booked",
                    after_json={"calendly_event_uri": external_id},
                    ip_address=request.client.host if request.client else None,
                )
            else:
                logger.info(
                    "calendly: no prospect for email=%s — recording delivery only",
                    invitee_email,
                )

        elif "invitee.canceled" in kind and invitee_email:
            prospect = await ProspectCRUD.get_by_email(db, invitee_email)
            # Only fire demo_no_show if the booked time was in the past
            # (i.e. they ghosted, not a pre-meeting cancel).
            scheduled_at_raw = (
                (payload_obj.get("scheduled_event") or {}).get("start_time")
                or payload_obj.get("event_start_time")
            )
            scheduled_in_past = False
            if scheduled_at_raw:
                from datetime import datetime as _dt, timezone as _tz
                try:
                    sched = _dt.fromisoformat(str(scheduled_at_raw).replace("Z", "+00:00"))
                    scheduled_in_past = sched <= _dt.now(_tz.utc)
                except ValueError:
                    scheduled_in_past = False
            if prospect is not None and scheduled_in_past:
                await CampaignEventCRUD.record(
                    db,
                    campaign_id=None,
                    prospect_id=prospect.id,
                    event_type=_EVENT_DEMO_NO_SHOW,
                    payload_json={"calendly_event_uri": external_id},
                )
                await AuditLogCRUD.record(
                    db,
                    actor_user_id=None,
                    entity_type="prospect",
                    entity_id=prospect.id,
                    action="calendly_demo_no_show",
                    after_json={"calendly_event_uri": external_id},
                    ip_address=request.client.host if request.client else None,
                )

        # 6. mark processed
        await WebhookDeliveryCRUD.mark_processed(db, delivery)
        return ok({"duplicate": False, "id": delivery.id}, message="webhook processed")

    except Exception as exc:  # noqa: BLE001 — record failure on the delivery row
        logger.exception("calendly_webhook processing failed: %s", exc)
        await WebhookDeliveryCRUD.mark_failed(db, delivery, str(exc))
        return fail("webhook processing failed", error=str(exc), data={"id": delivery.id})


@router.post("/apollo")
async def apollo_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """TODO: same pattern as Calendly. Provider=1. (Owned by Dev B.)"""
    payload = await request.json()
    external_id = str(payload.get("id", "unknown"))
    row, dup = await WebhookDeliveryCRUD.record(
        db, provider=_PROVIDER_APOLLO, external_event_id=external_id, payload_json=payload,
    )
    return ok({"duplicate": dup, "id": row.id})
