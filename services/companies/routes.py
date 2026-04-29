"""FastAPI routes for companies (Schema doc §7.2, §6.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.audit.crud import AuditLogCRUD
from services.common.envelope import ok

from .crud import CompanyCRUD
from .enums import COMPANY_SOURCES, get_label
from .schemas import CompanyCreate, CompanyOut, CompanyUpdate

router = APIRouter(prefix="/api/companies", tags=["companies"])


def _serialize(company) -> dict:
    out = CompanyOut.model_validate(company).model_dump(mode="json")
    out["source_label"] = get_label(COMPANY_SOURCES, company.source)
    return out


def _audit_payload(company) -> dict:
    return {"name": company.name, "domain": company.domain, "source": company.source}


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
async def create_company(
    payload: CompanyCreate,
    request: Request,
    actor_user_id: int | None = None,  # TODO replace with Depends(get_current_user) in auth-sweep
    db: AsyncSession = Depends(get_db),
) -> dict:
    if payload.domain and await CompanyCRUD.get_by_domain(db, payload.domain):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="company with this domain exists")
    company = await CompanyCRUD.create(db, **payload.model_dump())
    await AuditLogCRUD.record(
        db,
        actor_user_id=actor_user_id,
        entity_type="company",
        entity_id=company.id,
        action="create",
        after_json=_audit_payload(company),
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(company), message="company created")


@router.patch("/{company_id}")
async def update_company(
    company_id: int,
    payload: CompanyUpdate,
    request: Request,
    actor_user_id: int | None = None,  # TODO replace with Depends(get_current_user) in auth-sweep
    db: AsyncSession = Depends(get_db),
) -> dict:
    company = await CompanyCRUD.get_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company not found")
    before = _audit_payload(company)
    company = await CompanyCRUD.update(db, company, **payload.model_dump(exclude_unset=True))
    await AuditLogCRUD.record(
        db,
        actor_user_id=actor_user_id,
        entity_type="company",
        entity_id=company.id,
        action="update",
        before_json=before,
        after_json=_audit_payload(company),
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(company), message="company updated")


@router.delete("/{company_id}")
async def delete_company(
    company_id: int,
    request: Request,
    actor_user_id: int | None = None,  # TODO replace with Depends(get_current_user) in auth-sweep
    db: AsyncSession = Depends(get_db),
) -> dict:
    company = await CompanyCRUD.get_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company not found")
    await CompanyCRUD.soft_delete(db, company)
    await AuditLogCRUD.record(
        db,
        actor_user_id=actor_user_id,
        entity_type="company",
        entity_id=company.id,
        action="delete",
        ip_address=request.client.host if request.client else None,
    )
    return ok(message="company deleted")
