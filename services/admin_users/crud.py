"""
Async CRUD for admin_users.

Per architecture rules: this is the ONLY layer that touches the DB. Routes
call these methods; services never do. Methods are static and accept an
`AsyncSession` plus typed args.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AdminUser


class AdminUserCRUD:
    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> Optional[AdminUser]:
        result = await db.execute(
            select(AdminUser).where(AdminUser.id == user_id, AdminUser.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[AdminUser]:
        result = await db.execute(
            select(AdminUser).where(AdminUser.email == email, AdminUser.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(db: AsyncSession, role: Optional[int] = None) -> list[AdminUser]:
        stmt = select(AdminUser).where(AdminUser.deleted_at.is_(None))
        if role is not None:
            stmt = stmt.where(AdminUser.role == role)
        stmt = stmt.order_by(AdminUser.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        email: str,
        password_hash: str,
        first_name: str,
        last_name: Optional[str],
        role: int,
        daily_call_target: Optional[int] = None,
        avatar_color: Optional[str] = None,
    ) -> AdminUser:
        kwargs = dict(
            email=email,
            password_hash=password_hash,
            first_name=first_name,
            last_name=last_name,
            role=role,
            avatar_color=avatar_color,
        )
        if daily_call_target is not None:
            kwargs["daily_call_target"] = daily_call_target
        user = AdminUser(**kwargs)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def update(db: AsyncSession, user: AdminUser, **fields) -> AdminUser:
        for key, value in fields.items():
            if value is not None:
                setattr(user, key, value)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def soft_delete(db: AsyncSession, user: AdminUser) -> None:
        from datetime import datetime, timezone

        user.deleted_at = datetime.now(timezone.utc)
        await db.commit()

    @staticmethod
    async def update_last_login(db: AsyncSession, user: AdminUser) -> AdminUser:
        from datetime import datetime, timezone

        user.last_login_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(user)
        return user
