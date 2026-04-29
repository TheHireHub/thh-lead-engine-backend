"""Async CRUD for unsubscribes (Schema doc §7.14, Arch-26)."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Unsubscribe


class UnsubscribeCRUD:
    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[Unsubscribe]:
        result = await db.execute(select(Unsubscribe).where(Unsubscribe.email == email))
        return result.scalar_one_or_none()

    @staticmethod
    async def is_unsubscribed(db: AsyncSession, email: str) -> bool:
        return await UnsubscribeCRUD.get_by_email(db, email) is not None

    @staticmethod
    async def list_recent(
        db: AsyncSession,
        source_campaign_id: Optional[int] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Unsubscribe]:
        stmt = select(Unsubscribe)
        if source_campaign_id is not None:
            stmt = stmt.where(Unsubscribe.source_campaign_id == source_campaign_id)
        stmt = stmt.order_by(Unsubscribe.unsubscribed_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_or_create(
        db: AsyncSession,
        *,
        email: str,
        prospect_id: Optional[int] = None,
        source_campaign_id: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> tuple[Unsubscribe, bool]:
        """
        Idempotent: return (row, created). Race-safe — UNIQUE on email.

        On re-call with same email: returns existing row, created=False.
        """
        existing = await UnsubscribeCRUD.get_by_email(db, email)
        if existing:
            return existing, False
        row = Unsubscribe(
            email=email,
            prospect_id=prospect_id,
            source_campaign_id=source_campaign_id,
            reason=reason,
        )
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await UnsubscribeCRUD.get_by_email(db, email)
            if existing:
                return existing, False
            raise
        await db.refresh(row)
        return row, True
