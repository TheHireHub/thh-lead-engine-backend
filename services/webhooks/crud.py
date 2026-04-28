"""
Async CRUD for webhook_deliveries.

Per Arch-14: webhook security uses HMAC-SHA256 + timestamp window for replay
protection + this idempotency table. Inbound webhooks should:
1. Verify HMAC signature
2. Reject if external_event_id already exists (status=duplicate)
3. Insert this row with status=received, then enqueue ARQ task to process
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import WebhookDelivery


class WebhookDeliveryCRUD:
    @staticmethod
    async def get_by_external_id(
        db: AsyncSession, provider: int, external_event_id: str
    ) -> Optional[WebhookDelivery]:
        result = await db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.provider == provider,
                WebhookDelivery.external_event_id == external_event_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def record(
        db: AsyncSession,
        *,
        provider: int,
        external_event_id: str,
        payload_json: dict,
        signature: Optional[str] = None,
    ) -> tuple[WebhookDelivery, bool]:
        """Returns (row, was_duplicate)."""
        existing = await WebhookDeliveryCRUD.get_by_external_id(db, provider, external_event_id)
        if existing:
            return existing, True
        row = WebhookDelivery(
            provider=provider,
            external_event_id=external_event_id,
            signature=signature,
            payload_json=payload_json,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row, False

    @staticmethod
    async def mark_processed(db: AsyncSession, row: WebhookDelivery) -> None:
        row.status = 1  # processed
        row.processed_at = datetime.now(timezone.utc)
        await db.commit()

    @staticmethod
    async def mark_failed(db: AsyncSession, row: WebhookDelivery, error: str) -> None:
        row.status = 2  # failed
        row.error_message = error
        row.processed_at = datetime.now(timezone.utc)
        await db.commit()
