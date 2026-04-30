"""FastAPI routes for landing pages, variants, visits."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.deps import require_dashboard_read, require_growth, require_internal
from services.admin_users.models import AdminUser
from services.audit.crud import AuditLogCRUD
from services.common.envelope import ok
from services.prospects.promotion import promote_to_curious_on_visit

from .crud import LandingPageCRUD, LandingPageVariantCRUD, LandingPageVisitCRUD
from .hashing import hash_ip
from .schemas import (
    LandingPageCreate,
    LandingPageOut,
    RenderOut,
    VariantCreate,
    VariantOut,
    VariantPerformance,
    VariantStatusUpdate,
    VisitCreate,
    VisitsAggregateOut,
)
from .utm_mapping import OUTREACH, PAID, SEO, bucket_for
from .variant_picker import pick_variant

router = APIRouter(prefix="/api/landing-pages", tags=["landing_pages"])


# --------------------------------------------------------------- pages

@router.get("")
async def list_pages(
    prospect_id: Optional[int] = None,
    company_id: Optional[int] = None,
    template_key: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    pages = await LandingPageCRUD.list_all(
        db,
        prospect_id=prospect_id,
        company_id=company_id,
        template_key=template_key,
        limit=limit,
        offset=offset,
    )
    return ok([LandingPageOut.model_validate(p).model_dump() for p in pages])


@router.get("/by-slug/{slug}")
async def get_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    page = await LandingPageCRUD.get_by_slug(db, slug)
    if not page:
        raise HTTPException(status_code=404, detail="landing page not found")
    return ok(LandingPageOut.model_validate(page).model_dump())


@router.get("/by-slug/{slug}/render")
async def render_by_slug(
    slug: str,
    visitor_id: str = Query(..., min_length=1, max_length=64),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Public render endpoint. Used by the frontend's `/lp/[slug]` page.

    Picks an A/B variant deterministically per visitor (Schema doc Arch-31)
    and returns `{page, picked_variant, content_json}`. If no active variants,
    falls back to the page's `default_content_json`.
    """
    page = await LandingPageCRUD.get_by_slug(db, slug)
    if not page:
        raise HTTPException(status_code=404, detail="landing page not found")

    active_variants = await LandingPageVariantCRUD.list_active_for_page(db, page.id)
    picked = pick_variant(active_variants, visitor_id)
    content = (picked.content_json if picked else page.default_content_json) or {}

    return ok(
        RenderOut(
            page=LandingPageOut.model_validate(page),
            picked_variant=VariantOut.model_validate(picked) if picked else None,
            content_json=content,
        ).model_dump()
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_page(
    payload: LandingPageCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_growth),
) -> dict:
    if await LandingPageCRUD.get_by_slug(db, payload.slug):
        raise HTTPException(status_code=409, detail="slug already in use")
    page = await LandingPageCRUD.create(db, **payload.model_dump(exclude_none=True))
    await AuditLogCRUD.record(
        db,
        entity_type="landing_page",
        entity_id=page.id,
        action="create",
        after_json={"slug": page.slug, "template_key": page.template_key},
    )
    return ok(LandingPageOut.model_validate(page).model_dump(), message="landing page created")


# --------------------------------------------------------------- variants

@router.post("/variants", status_code=status.HTTP_201_CREATED)
async def create_variant(
    payload: VariantCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_growth),
) -> dict:
    page = await LandingPageCRUD.get_by_id(db, payload.landing_page_id)
    if not page:
        raise HTTPException(status_code=404, detail="landing page not found")
    variant = await LandingPageVariantCRUD.create(db, **payload.model_dump())
    await AuditLogCRUD.record(
        db,
        entity_type="landing_page_variant",
        entity_id=variant.id,
        action="create",
        after_json={
            "landing_page_id": payload.landing_page_id,
            "variant_key": payload.variant_key,
            "weight": payload.weight,
        },
    )
    return ok(VariantOut.model_validate(variant).model_dump(), message="variant created")


@router.patch("/variants/{variant_id}/status")
async def update_variant_status(
    variant_id: int,
    payload: VariantStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_growth),
) -> dict:
    variant = await LandingPageVariantCRUD.get_by_id(db, variant_id)
    if not variant:
        raise HTTPException(status_code=404, detail="variant not found")
    before = variant.status
    variant = await LandingPageVariantCRUD.update_status(db, variant, payload.status)
    await AuditLogCRUD.record(
        db,
        entity_type="landing_page_variant",
        entity_id=variant.id,
        action="status_change",
        before_json={"status": before},
        after_json={"status": variant.status},
    )
    return ok(VariantOut.model_validate(variant).model_dump(), message="variant status updated")


@router.get("/{page_id}/variants/performance")
async def variant_performance(
    page_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    """Per-variant analytics: visit_count, signup_count, computed signup_rate."""
    page = await LandingPageCRUD.get_by_id(db, page_id)
    if not page:
        raise HTTPException(status_code=404, detail="landing page not found")
    variants = await LandingPageVariantCRUD.list_for_page(db, page_id)
    rows = [
        VariantPerformance(
            id=v.id,
            variant_key=v.variant_key,
            status=v.status,
            weight=v.weight,
            visit_count=v.visit_count,
            signup_count=v.signup_count,
            signup_rate=(v.signup_count / v.visit_count) if v.visit_count else 0.0,
        ).model_dump()
        for v in variants
    ]
    return ok(rows)


# --------------------------------------------------------------- visits

@router.get("/visits/aggregate")
async def visits_aggregate(
    from_date: date = Query(...),
    to_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """
    Visits aggregated by marketing-channel bucket (Funnel Board "Visits"
    widget). Pulls every `landing_page_visits` row in
    `[from_date, to_date]` inclusive, groups by `utm_source`, then folds
    each source into one of `seo|paid|outreach` via
    `services.landing_pages.utm_mapping.bucket_for`.
    """
    rows = await LandingPageVisitCRUD.aggregate_by_utm_source(
        db, from_date=from_date, to_date=to_date
    )
    by_source: dict[str, int] = {SEO: 0, PAID: 0, OUTREACH: 0}
    total = 0
    for utm_source, count in rows:
        by_source[bucket_for(utm_source)] += count
        total += count

    return ok(
        VisitsAggregateOut(
            from_date=from_date,
            to_date=to_date,
            total=total,
            by_source=by_source,
        ).model_dump(mode="json")
    )


@router.post("/visits", status_code=status.HTTP_201_CREATED)
async def record_visit(
    payload: VisitCreate,
    request: Request,
    prospect_id: Optional[int] = Query(default=None, description="if known, links visit to prospect"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Record a landing page visit.

    Side effects (Schema doc §7.11):
    1. Hash IP via VISITOR_IP_HASH_SECRET (never store raw IP).
    2. Pull user_agent from request headers.
    3. Bump landing_pages.visit_count + last_visit_at.
    4. Bump landing_page_variants.visit_count if a variant was shown.
    5. If prospect_id is set, fire Cold→Curious auto-promotion.
       (TODO Dev A handoff: services.prospects.promotion.promote_to_curious_on_visit)
    """
    page = await LandingPageCRUD.get_by_id(db, payload.landing_page_id)
    if not page:
        raise HTTPException(status_code=404, detail="landing page not found")

    # Pull IP from X-Forwarded-For (proxy-aware) → fallback to client.host
    fwd = request.headers.get("x-forwarded-for", "")
    raw_ip = (fwd.split(",")[0].strip() if fwd else None) or (
        request.client.host if request.client else None
    )

    visit_fields = payload.model_dump(exclude_none=True)
    visit_fields["ip_hash"] = hash_ip(raw_ip)
    visit_fields["user_agent"] = request.headers.get("user-agent")
    if prospect_id is not None:
        visit_fields["prospect_id"] = prospect_id

    visit = await LandingPageVisitCRUD.record(db, **visit_fields)

    await LandingPageCRUD.bump_visit(db, page)
    if payload.landing_page_variant_id:
        variant = await LandingPageVariantCRUD.get_by_id(db, payload.landing_page_variant_id)
        if variant:
            await LandingPageVariantCRUD.bump_visit(db, variant)

    # md Arch-37 / §3: any landing page visit promotes prospect cold→curious.
    # `promote_to_curious_on_visit` is idempotent — no-ops if stage != cold.
    promoted = False
    if prospect_id is not None:
        promoted = await promote_to_curious_on_visit(db, prospect_id)

    return ok({"id": visit.id, "promoted_to_curious": promoted}, message="visit recorded")
