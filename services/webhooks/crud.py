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
        """Returns (row, was_duplicate).

        Status semantics for replay:
          - status=0 received / status=1 processed → treat as duplicate
          - status=2 failed → reset to received, refresh payload, allow replay
            (a prior crash dropped the event; re-pushing with the same
            dedup_key must succeed, otherwise the failure is permanent).
        """
        existing = await WebhookDeliveryCRUD.get_by_external_id(db, provider, external_event_id)
        if existing is not None:
            if existing.status == 2:
                # Reset failure state and let the caller re-process.
                existing.status = 0
                existing.error_message = None
                existing.processed_at = None
                existing.payload_json = payload_json
                if signature is not None:
                    existing.signature = signature
                await db.commit()
                await db.refresh(existing)
                return existing, False
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

    @staticmethod
    async def count_failed(db: AsyncSession) -> int:
        """Number of webhook_deliveries rows where ingest crashed (status=2).
        Surfaced on the admin management dashboard so silent push drops get
        noticed within hours, not days."""
        from sqlalchemy import func
        result = await db.execute(
            select(func.count(WebhookDelivery.id)).where(WebhookDelivery.status == 2)
        )
        return int(result.scalar_one() or 0)

    @staticmethod
    async def list_failed(
        db: AsyncSession, *, limit: int = 50
    ) -> list[WebhookDelivery]:
        """Most recent failed deliveries (status=2), newest first."""
        result = await db.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.status == 2)
            .order_by(WebhookDelivery.received_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
