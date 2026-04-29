"""Async CRUD for companies (Schema doc §7.2, §6.4, Arch-9)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
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
        db: AsyncSession,
        source: Optional[int] = None,
        industry: Optional[str] = None,
        funding_stage: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Company]:
        stmt = select(Company).where(Company.deleted_at.is_(None))
        if source is not None:
            stmt = stmt.where(Company.source == source)
        if industry:
            stmt = stmt.where(Company.industry == industry)
        if funding_stage:
            stmt = stmt.where(Company.funding_stage == funding_stage)
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(Company.name.ilike(like), Company.domain.ilike(like))
            )
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

    @staticmethod
    async def get_or_create_by_domain(
        db: AsyncSession,
        *,
        domain: str,
        name: str,
        source: int = 1,
        **defaults,
    ) -> tuple[Company, bool]:
        """Idempotent upsert by domain. Returns (company, created)."""
        existing = await CompanyCRUD.get_by_domain(db, domain)
        if existing:
            return existing, False
        company = Company(name=name, domain=domain, source=source, **defaults)
        db.add(company)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await CompanyCRUD.get_by_domain(db, domain)
            if existing:
                return existing, False
            raise
        await db.refresh(company)
        return company, True

    @staticmethod
    async def mark_enriched(db: AsyncSession, company: Company, **fields) -> Company:
        for key, value in fields.items():
            if value is not None:
                setattr(company, key, value)
        company.enriched_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(company)
        return company
