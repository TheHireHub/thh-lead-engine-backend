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

from services.common.environment import env_filter_clause

from .models import WebhookDelivery


def _reset_for_replay(
    row: WebhookDelivery, payload_json: dict, signature: Optional[str]
) -> None:
    """In-place reset of a failed (status=2) delivery so its dedup_key can
    re-ingest. Caller commits."""
    row.status = 0
    row.error_message = None
    row.processed_at = None
    row.payload_json = payload_json
    if signature is not None:
        row.signature = signature


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
        environment: Optional[int] = None,
    ) -> tuple[WebhookDelivery, bool]:
        """Returns (row, was_duplicate).

        Status semantics for replay:
          - status=0 received / status=1 processed → treat as duplicate
          - status=2 failed → reset to received, refresh payload, allow replay
            (a prior crash dropped the event; re-pushing with the same
            dedup_key must succeed, otherwise the failure is permanent).

        `environment` is stamped on the row only when creating a new
        delivery. Replay-after-failure preserves the original env tag.
        """
        existing = await WebhookDeliveryCRUD.get_by_external_id(db, provider, external_event_id)
        if existing is not None:
            if existing.status == 2:
                _reset_for_replay(existing, payload_json, signature)
                await db.commit()
                await db.refresh(existing)
                return existing, False
            return existing, True
        row = WebhookDelivery(
            provider=provider,
            external_event_id=external_event_id,
            signature=signature,
            payload_json=payload_json,
            environment=environment,
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
        db: AsyncSession, *, limit: int = 50, environment: Optional[int] = None
    ) -> list[WebhookDelivery]:
        """Most recent failed deliveries (status=2), newest first."""
        stmt = (
            select(WebhookDelivery)
            .where(WebhookDelivery.status == 2)
            .order_by(WebhookDelivery.received_at.desc())
            .limit(limit)
        )
        env_clause = env_filter_clause(WebhookDelivery.environment, environment)
        if env_clause is not None:
            stmt = stmt.where(env_clause)
        result = await db.execute(stmt)
        return list(result.scalars().all())
