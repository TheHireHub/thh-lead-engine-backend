"""FastAPI routes for inbound webhooks (Schema doc §7.18, Arch-13, Arch-14)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.audit.crud import AuditLogCRUD
from services.campaigns.crud import CampaignEventCRUD
from services.common.envelope import fail, ok
from services.prospects.crud import ProspectCRUD
from services.prospects.models import Prospect, ProspectChannel

from .crud import WebhookDeliveryCRUD

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

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


def _verify_apollo_signature(body: bytes, signature: Optional[str]) -> bool:
    """
    Apollo doesn't always sign webhooks — only enforce when both the env
    secret AND the inbound header are present. Returns True if either:
      * signing isn't configured (skip), or
      * HMAC-SHA256(body, secret) matches the header.
    """
    secret = os.getenv("APOLLO_WEBHOOK_SIGNING_KEY", "")
    if not secret:
        return True  # not configured -> accept
    if not signature:
        return False
    expected = hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _upsert_prospect_from_apollo(
    db: AsyncSession, payload: dict
) -> Optional[int]:
    """
    Minimal Apollo prospect upsert.

    Looks up by `apollo_contact_id` first, falls back to `linkedin_url`.
    Updates a small set of fields if the prospect exists; otherwise inserts.

    NOTE: this duplicates a piece of what Dev A's
    services.prospects.dedupe.find_existing will do (DEV_A Step 3.1).
    Once that ships, swap this for a single call to it. Until then, this
    keeps the inbound webhook from blocking on the cross-lane dependency.
    """
    contact = (payload.get("data") or payload.get("person") or {})
    if not contact:
        return None

    apollo_contact_id = str(contact.get("id") or contact.get("apollo_contact_id") or "")
    linkedin_url = contact.get("linkedin_url")
    email = contact.get("email")
    first_name = contact.get("first_name")
    last_name = contact.get("last_name")
    title = contact.get("title")

    prospect: Optional[Prospect] = None
    if apollo_contact_id:
        result = await db.execute(
            select(Prospect).where(
                Prospect.apollo_contact_id == apollo_contact_id,
                Prospect.deleted_at.is_(None),
            )
        )
        prospect = result.scalar_one_or_none()
    if prospect is None and linkedin_url:
        result = await db.execute(
            select(Prospect).where(
                Prospect.linkedin_url == linkedin_url,
                Prospect.deleted_at.is_(None),
            )
        )
        prospect = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if prospect is None:
        # Need at least one identifier to insert.
        if not (apollo_contact_id or linkedin_url or email):
            return None
        prospect = Prospect(
            apollo_contact_id=apollo_contact_id or None,
            linkedin_url=linkedin_url,
            email=email,
            first_name=first_name,
            last_name=last_name,
            title=title,
            source_channel=9,  # apollo (§6.3)
            stage=0,  # cold
            heat_level=0,
            heat_score=0,
            quality_score=0,
            touch_count=0,
            jobs_created_count=0,
            applicants_received_count=0,
            rnr_count=0,
            first_touched_at=now,
            last_touched_at=now,
        )
        db.add(prospect)
        await db.flush()  # get id without committing yet
    else:
        # Update non-destructively — only fill blanks + bump touch.
        if not prospect.apollo_contact_id and apollo_contact_id:
            prospect.apollo_contact_id = apollo_contact_id
        if not prospect.linkedin_url and linkedin_url:
            prospect.linkedin_url = linkedin_url
        if not prospect.email and email:
            prospect.email = email
        if not prospect.first_name and first_name:
            prospect.first_name = first_name
        if not prospect.last_name and last_name:
            prospect.last_name = last_name
        if not prospect.title and title:
            prospect.title = title
        prospect.last_touched_at = now
        prospect.touch_count = (prospect.touch_count or 0) + 1

    # Touch the apollo channel.
    result = await db.execute(
        select(ProspectChannel).where(
            ProspectChannel.prospect_id == prospect.id,
            ProspectChannel.channel == 9,
        )
    )
    ch = result.scalar_one_or_none()
    if ch is None:
        db.add(
            ProspectChannel(
                prospect_id=prospect.id,
                channel=9,
                touch_count=1,
                first_touched_at=now,
                last_touched_at=now,
            )
        )
    else:
        ch.touch_count = (ch.touch_count or 0) + 1
        ch.last_touched_at = now

    await db.commit()
    return prospect.id


@router.post("/apollo")
async def apollo_webhook(
    request: Request,
    apollo_signature: Optional[str] = Header(default=None, alias="X-Apollo-Signature"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Inbound Apollo webhook.

    1. Optional HMAC verification (only enforced when APOLLO_WEBHOOK_SIGNING_KEY
       is set in env).
    2. Idempotent record via webhook_deliveries (provider=1, unique key on
       (provider, external_event_id)).
    3. On prospect.created / prospect.updated: upsert into `prospects`
       by apollo_contact_id (fallback linkedin_url), bump apollo channel
       touch.
    4. Mark webhook row processed (or failed with error_message).
    """
    raw_body = await request.body()
    if not _verify_apollo_signature(raw_body, apollo_signature):
        logger.warning("apollo webhook: signature mismatch")
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("apollo webhook: bad json: %s", exc)
        raise HTTPException(status_code=400, detail="invalid JSON")

    external_id = str(
        payload.get("id")
        or payload.get("event_id")
        or (payload.get("data") or {}).get("id", "unknown")
    )
    row, dup = await WebhookDeliveryCRUD.record(
        db,
        provider=_PROVIDER_APOLLO,
        external_event_id=external_id,
        payload_json=payload,
        signature=apollo_signature,
    )
    if dup:
        return ok({"duplicate": True, "id": row.id})

    event_type = payload.get("event") or payload.get("type") or ""
    prospect_id: Optional[int] = None
    try:
        if event_type in ("prospect.created", "prospect.updated", "person.created", "person.updated"):
            prospect_id = await _upsert_prospect_from_apollo(db, payload)
        await WebhookDeliveryCRUD.mark_processed(db, row)
        await AuditLogCRUD.record(
            db,
            entity_type="webhook_delivery",
            entity_id=row.id,
            action="apollo_processed",
            after_json={
                "event_type": event_type,
                "prospect_id": prospect_id,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("apollo webhook process failed")
        await WebhookDeliveryCRUD.mark_failed(db, row, str(exc))

    return ok(
        {"duplicate": False, "id": row.id, "prospect_id": prospect_id},
        message="apollo webhook processed",
    )
