"""Async CRUD for unsubscribes."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
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
    async def create(db: AsyncSession, **fields) -> Unsubscribe:
        row = Unsubscribe(**fields)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row
