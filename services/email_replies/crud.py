"""Async CRUD for email_replies."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import EmailReply


class EmailReplyCRUD:
    @staticmethod
    async def get_by_id(db: AsyncSession, reply_id: int) -> Optional[EmailReply]:
        result = await db.execute(select(EmailReply).where(EmailReply.id == reply_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_prospect(db: AsyncSession, prospect_id: int) -> list[EmailReply]:
        result = await db.execute(
            select(EmailReply)
            .where(EmailReply.prospect_id == prospect_id)
            .order_by(EmailReply.received_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, **fields) -> EmailReply:
        reply = EmailReply(**fields)
        db.add(reply)
        await db.commit()
        await db.refresh(reply)
        return reply
