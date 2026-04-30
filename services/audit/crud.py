"""
Async CRUD for audit_log.

Per Arch-18: ONE generic table for all entities. Every service that mutates
state should call `AuditLogCRUD.record(...)` in the same transaction or
immediately after, so we have a unified compliance trail.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog


class AuditLogCRUD:
    @staticmethod
    async def record(
        db: AsyncSession,
        *,
        entity_type: str,
        action: str,
        entity_id: Optional[int] = None,
        actor_user_id: Optional[int] = None,
        before_json: Optional[dict] = None,
        after_json: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> AuditLog:
        row = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            before_json=before_json,
            after_json=after_json,
            ip_address=ip_address,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def list_for_entity(
        db: AsyncSession, entity_type: str, entity_id: int, limit: int = 100
    ) -> list[AuditLog]:
        result = await db.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_for_actor(db: AsyncSession, actor_user_id: int, limit: int = 100) -> list[AuditLog]:
        result = await db.execute(
            select(AuditLog)
            .where(AuditLog.actor_user_id == actor_user_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_by_action(
        db: AsyncSession, action: str, limit: int = 100, offset: int = 0
    ) -> list[AuditLog]:
        result = await db.execute(
            select(AuditLog)
            .where(AuditLog.action == action)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_recent(db: AsyncSession, limit: int = 50) -> list[AuditLog]:
        """Last N audit events across all entities. Powers the admin Audit Log page."""
        result = await db.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
