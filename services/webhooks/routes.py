"""FastAPI routes for inbound webhooks (Calendly, Apollo, email provider)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.audit.crud import AuditLogCRUD
from services.common.envelope import ok
from services.prospects.models import Prospect, ProspectChannel

from .crud import WebhookDeliveryCRUD

logger = logging.getLogger(__name__)

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
        provider=1,
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
