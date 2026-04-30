"""Async CRUD for landing pages, variants, visits."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select
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
    async def list_all(
        db: AsyncSession,
        *,
        prospect_id: Optional[int] = None,
        company_id: Optional[int] = None,
        template_key: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LandingPage]:
        stmt = select(LandingPage).where(LandingPage.deleted_at.is_(None))
        if prospect_id is not None:
            stmt = stmt.where(LandingPage.prospect_id == prospect_id)
        if company_id is not None:
            stmt = stmt.where(LandingPage.company_id == company_id)
        if template_key is not None:
            stmt = stmt.where(LandingPage.template_key == template_key)
        stmt = stmt.order_by(LandingPage.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, **fields) -> LandingPage:
        page = LandingPage(**fields)
        db.add(page)
        await db.commit()
        await db.refresh(page)
        return page

    @staticmethod
    async def bump_visit(db: AsyncSession, page: LandingPage) -> None:
        """Increment visit_count + set last_visit_at."""
        page.visit_count = (page.visit_count or 0) + 1
        page.last_visit_at = datetime.now(timezone.utc)
        await db.commit()


class LandingPageVariantCRUD:
    @staticmethod
    async def get_by_id(db: AsyncSession, variant_id: int) -> Optional[LandingPageVariant]:
        result = await db.execute(
            select(LandingPageVariant).where(
                LandingPageVariant.id == variant_id,
                LandingPageVariant.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_active_for_page(
        db: AsyncSession, landing_page_id: int
    ) -> list[LandingPageVariant]:
        result = await db.execute(
            select(LandingPageVariant).where(
                LandingPageVariant.landing_page_id == landing_page_id,
                LandingPageVariant.status == 0,
                LandingPageVariant.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_for_page(
        db: AsyncSession, landing_page_id: int
    ) -> list[LandingPageVariant]:
        """All variants regardless of status — for the performance endpoint."""
        result = await db.execute(
            select(LandingPageVariant).where(
                LandingPageVariant.landing_page_id == landing_page_id,
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

    @staticmethod
    async def bump_visit(db: AsyncSession, variant: LandingPageVariant) -> None:
        variant.visit_count = (variant.visit_count or 0) + 1
        await db.commit()

    @staticmethod
    async def bump_signup(db: AsyncSession, variant: LandingPageVariant) -> None:
        variant.signup_count = (variant.signup_count or 0) + 1
        await db.commit()

    @staticmethod
    async def update_status(
        db: AsyncSession, variant: LandingPageVariant, status: int
    ) -> LandingPageVariant:
        variant.status = status
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

    @staticmethod
    async def latest_for_visitor(
        db: AsyncSession, visitor_id: str
    ) -> Optional[LandingPageVisit]:
        """
        Most recent visit by a visitor — used to attribute a downstream signup
        to the variant they were shown.
        """
        result = await db.execute(
            select(LandingPageVisit)
            .where(LandingPageVisit.visitor_id == visitor_id)
            .order_by(LandingPageVisit.visited_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def variant_visit_count(db: AsyncSession, variant_id: int) -> int:
        """Live count from the visits table — sanity-check vs the denormalised counter."""
        result = await db.execute(
            select(func.count(LandingPageVisit.id)).where(
                LandingPageVisit.landing_page_variant_id == variant_id
            )
        )
        return result.scalar_one() or 0

    @staticmethod
    async def aggregate_by_utm_source(
        db: AsyncSession, *, from_date: date, to_date: date
    ) -> list[tuple[Optional[str], int]]:
        """
        Group visits in the [from_date, to_date] inclusive window by raw
        utm_source. Returns `[(utm_source, count), ...]` — bucketing into
        SEO/Paid/Outreach happens in the route via `utm_mapping.bucket_for`
        so the mapping stays a route-level concern.
        """
        stmt = (
            select(LandingPageVisit.utm_source, func.count(LandingPageVisit.id))
            .where(
                func.date(LandingPageVisit.visited_at) >= from_date,
                func.date(LandingPageVisit.visited_at) <= to_date,
            )
            .group_by(LandingPageVisit.utm_source)
        )
        result = await db.execute(stmt)
        return [(src, int(cnt or 0)) for src, cnt in result.all()]
