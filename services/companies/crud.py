"""Async CRUD for companies."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Company


class CompanyCRUD:
    @staticmethod
    async def get_by_id(db: AsyncSession, company_id: int) -> Optional[Company]:
        result = await db.execute(
            select(Company).where(Company.id == company_id, Company.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_domain(db: AsyncSession, domain: str) -> Optional[Company]:
        result = await db.execute(
            select(Company).where(Company.domain == domain, Company.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession, source: Optional[int] = None, limit: int = 100, offset: int = 0
    ) -> list[Company]:
        stmt = select(Company).where(Company.deleted_at.is_(None))
        if source is not None:
            stmt = stmt.where(Company.source == source)
        stmt = stmt.order_by(Company.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, **fields) -> Company:
        company = Company(**fields)
        db.add(company)
        await db.commit()
        await db.refresh(company)
        return company

    @staticmethod
    async def update(db: AsyncSession, company: Company, **fields) -> Company:
        for key, value in fields.items():
            if value is not None:
                setattr(company, key, value)
        await db.commit()
        await db.refresh(company)
        return company

    @staticmethod
    async def soft_delete(db: AsyncSession, company: Company) -> None:
        company.deleted_at = datetime.now(timezone.utc)
        await db.commit()
