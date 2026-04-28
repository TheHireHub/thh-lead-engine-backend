"""FastAPI routes for landing pages, variants, visits."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.common.envelope import ok

from .crud import LandingPageCRUD, LandingPageVariantCRUD, LandingPageVisitCRUD
from .schemas import LandingPageCreate, LandingPageOut, VariantCreate, VisitCreate

router = APIRouter(prefix="/api/landing-pages", tags=["landing_pages"])


@router.get("/")
async def list_pages(limit: int = 100, offset: int = 0, db: AsyncSession = Depends(get_db)) -> dict:
    pages = await LandingPageCRUD.list_all(db, limit=limit, offset=offset)
    return ok([LandingPageOut.model_validate(p).model_dump() for p in pages])


@router.get("/by-slug/{slug}")
async def get_by_slug(slug: str, db: AsyncSession = Depends(get_db)) -> dict:
    page = await LandingPageCRUD.get_by_slug(db, slug)
    if not page:
        raise HTTPException(status_code=404, detail="landing page not found")
    return ok(LandingPageOut.model_validate(page).model_dump())


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_page(payload: LandingPageCreate, db: AsyncSession = Depends(get_db)) -> dict:
    if await LandingPageCRUD.get_by_slug(db, payload.slug):
        raise HTTPException(status_code=409, detail="slug already in use")
    page = await LandingPageCRUD.create(db, **payload.model_dump(exclude_none=True))
    return ok(LandingPageOut.model_validate(page).model_dump(), message="landing page created")


@router.post("/variants", status_code=status.HTTP_201_CREATED)
async def create_variant(payload: VariantCreate, db: AsyncSession = Depends(get_db)) -> dict:
    variant = await LandingPageVariantCRUD.create(db, **payload.model_dump())
    return ok({"id": variant.id}, message="variant created")


@router.post("/visits", status_code=status.HTTP_201_CREATED)
async def record_visit(payload: VisitCreate, db: AsyncSession = Depends(get_db)) -> dict:
    # TODO: hash IP via VISITOR_IP_HASH_SECRET, attach user_agent from request headers.
    visit = await LandingPageVisitCRUD.record(db, **payload.model_dump(exclude_none=True))
    return ok({"id": visit.id}, message="visit recorded")
