"""Async CRUD for signups."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Signup


class SignupCRUD:
    @staticmethod
    async def get_by_id(db: AsyncSession, signup_id: int) -> Optional[Signup]:
        result = await db.execute(select(Signup).where(Signup.id == signup_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_recent(db: AsyncSession, limit: int = 100) -> list[Signup]:
        result = await db.execute(
            select(Signup).order_by(Signup.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, **fields) -> Signup:
        signup = Signup(**fields)
        db.add(signup)
        await db.commit()
        await db.refresh(signup)
        return signup

    @staticmethod
    async def mark_otp_verified(db: AsyncSession, signup: Signup) -> Signup:
        signup.otp_verified_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(signup)
        return signup
