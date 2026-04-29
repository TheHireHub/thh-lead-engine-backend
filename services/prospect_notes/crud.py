"""Async CRUD for prospect_notes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ProspectNote


class ProspectNoteCRUD:
    @staticmethod
    async def get_by_id(db: AsyncSession, note_id: int) -> Optional[ProspectNote]:
        result = await db.execute(
            select(ProspectNote).where(ProspectNote.id == note_id, ProspectNote.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_prospect(db: AsyncSession, prospect_id: int) -> list[ProspectNote]:
        result = await db.execute(
            select(ProspectNote)
            .where(ProspectNote.prospect_id == prospect_id, ProspectNote.deleted_at.is_(None))
            .order_by(ProspectNote.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_open_tasks_for_user(db: AsyncSession, user_id: int) -> list[ProspectNote]:
        result = await db.execute(
            select(ProspectNote).where(
                ProspectNote.assigned_to_user_id == user_id,
                ProspectNote.status == 1,
                ProspectNote.deleted_at.is_(None),
            ).order_by(ProspectNote.due_date.asc().nullslast())
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, **fields) -> ProspectNote:
        note = ProspectNote(**fields)
        db.add(note)
        await db.commit()
        await db.refresh(note)
        return note

    @staticmethod
    async def update(db: AsyncSession, note: ProspectNote, **fields) -> ProspectNote:
        for k, v in fields.items():
            if v is not None:
                setattr(note, k, v)
        await db.commit()
        await db.refresh(note)
        return note

    @staticmethod
    async def soft_delete(db: AsyncSession, note: ProspectNote) -> None:
        note.deleted_at = datetime.now(timezone.utc)
        await db.commit()

    @staticmethod
    async def list_recent(
        db: AsyncSession,
        prospect_id: Optional[int] = None,
        status: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProspectNote]:
        stmt = select(ProspectNote).where(ProspectNote.deleted_at.is_(None))
        if prospect_id is not None:
            stmt = stmt.where(ProspectNote.prospect_id == prospect_id)
        if status is not None:
            stmt = stmt.where(ProspectNote.status == status)
        stmt = stmt.order_by(ProspectNote.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def complete_task(db: AsyncSession, note: ProspectNote) -> ProspectNote:
        """Flip task_open(1) -> task_done(2). No-op for plain notes (status=0)."""
        if note.status == 1:
            note.status = 2
        await db.commit()
        await db.refresh(note)
        return note
