"""FastAPI routes for companies (Schema doc §7.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.common.envelope import ok

from .crud import CompanyCRUD
from .enums import COMPANY_SOURCES, get_label
from .schemas import CompanyCreate, CompanyOut, CompanyUpdate

router = APIRouter(prefix="/api/companies", tags=["companies"])


def _serialize(company) -> dict:
    out = CompanyOut.model_validate(company).model_dump()
    out["source_label"] = get_label(COMPANY_SOURCES, company.source)
    return out


@router.get("/")
async def list_companies(
    source: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> dict:
    companies = await CompanyCRUD.list_all(db, source=source, limit=limit, offset=offset)
    return ok([_serialize(c) for c in companies])


@router.get("/{company_id}")
async def get_company(company_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    company = await CompanyCRUD.get_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company not found")
    return ok(_serialize(company))


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_company(payload: CompanyCreate, db: AsyncSession = Depends(get_db)) -> dict:
    if payload.domain and await CompanyCRUD.get_by_domain(db, payload.domain):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="company with this domain exists")
    company = await CompanyCRUD.create(db, **payload.model_dump())
    return ok(_serialize(company), message="company created")


@router.patch("/{company_id}")
async def update_company(
    company_id: int, payload: CompanyUpdate, db: AsyncSession = Depends(get_db)
) -> dict:
    company = await CompanyCRUD.get_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company not found")
    company = await CompanyCRUD.update(db, company, **payload.model_dump(exclude_unset=True))
    return ok(_serialize(company), message="company updated")


@router.delete("/{company_id}")
async def delete_company(company_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    company = await CompanyCRUD.get_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company not found")
    await CompanyCRUD.soft_delete(db, company)
    return ok(message="company deleted")
