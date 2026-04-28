"""Async CRUD for landing pages, variants, visits."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import LandingPage, LandingPageVariant, LandingPageVisit


class LandingPageCRUD:
    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Optional[LandingPage]:
        result = await db.execute(
            select(LandingPage).where(LandingPage.slug == slug, LandingPage.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, page_id: int) -> Optional[LandingPage]:
        result = await db.execute(
            select(LandingPage).where(LandingPage.id == page_id, LandingPage.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(db: AsyncSession, limit: int = 100, offset: int = 0) -> list[LandingPage]:
        stmt = (
            select(LandingPage).where(LandingPage.deleted_at.is_(None))
            .order_by(LandingPage.created_at.desc()).limit(limit).offset(offset)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, **fields) -> LandingPage:
        page = LandingPage(**fields)
        db.add(page)
        await db.commit()
        await db.refresh(page)
        return page


class LandingPageVariantCRUD:
    @staticmethod
    async def list_active_for_page(db: AsyncSession, landing_page_id: int) -> list[LandingPageVariant]:
        result = await db.execute(
            select(LandingPageVariant).where(
                LandingPageVariant.landing_page_id == landing_page_id,
                LandingPageVariant.status == 0,
                LandingPageVariant.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, **fields) -> LandingPageVariant:
        variant = LandingPageVariant(**fields)
        db.add(variant)
        await db.commit()
        await db.refresh(variant)
        return variant


class LandingPageVisitCRUD:
    @staticmethod
    async def record(db: AsyncSession, **fields) -> LandingPageVisit:
        visit = LandingPageVisit(**fields)
        db.add(visit)
        await db.commit()
        await db.refresh(visit)
        return visit
