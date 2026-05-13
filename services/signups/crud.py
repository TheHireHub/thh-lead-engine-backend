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
    async def list_filtered(
        db: AsyncSession,
        *,
        request_type: Optional[int] = None,
        otp_verified: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Signup]:
        stmt = select(Signup)
        if request_type is not None:
            stmt = stmt.where(Signup.request_type == request_type)
        if otp_verified is True:
            stmt = stmt.where(Signup.otp_verified_at.is_not(None))
        elif otp_verified is False:
            stmt = stmt.where(Signup.otp_verified_at.is_(None))
        stmt = stmt.order_by(Signup.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_recent(db: AsyncSession, limit: int = 100) -> list[Signup]:
        return await SignupCRUD.list_filtered(db, limit=limit)

    @staticmethod
    async def list_for_lead(
        db: AsyncSession,
        *,
        prospect_id: Optional[int],
        email: Optional[str],
        limit: int = 200,
    ) -> list[Signup]:
        """Every signup event for a single lead, oldest→newest.

        Mirrors the FE grouping rule in `/signups`: when the row has a
        prospect_id, the lead is the union of all signups carrying that id;
        otherwise the lead is keyed by email and only un-attached signups
        belong to it. Powers the drawer Timeline so sales can see how the
        lead progressed before its latest event.
        """
        if prospect_id is not None:
            stmt = (
                select(Signup)
                .where(Signup.prospect_id == prospect_id)
                .order_by(Signup.created_at.asc())
                .limit(limit)
            )
        elif email:
            stmt = (
                select(Signup)
                .where(Signup.email == email, Signup.prospect_id.is_(None))
                .order_by(Signup.created_at.asc())
                .limit(limit)
            )
        else:
            return []
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, **fields) -> Signup:
        signup = Signup(**fields)
        db.add(signup)
        await db.commit()
        await db.refresh(signup)
        return signup

    @staticmethod
    async def attach_prospect(db: AsyncSession, signup: Signup, prospect_id: int) -> Signup:
        signup.prospect_id = prospect_id
        await db.commit()
        await db.refresh(signup)
        return signup

    @staticmethod
    async def mark_otp_verified(db: AsyncSession, signup: Signup) -> Signup:
        signup.otp_verified_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(signup)
        return signup
