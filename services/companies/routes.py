"""FastAPI routes for companies (Schema doc §7.2, §6.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.deps import (
    require_admin,
    require_dashboard_read,
    require_growth_or_bdr,
    require_internal,
    require_internal_or_caller,
)
from services.admin_users.models import AdminUser
from services.audit.crud import AuditLogCRUD
from services.common.envelope import ok
from services.common.environment import current_environment_from_query

from .crud import CompanyCRUD
from .enums import COMPANY_SOURCES, get_label
from .schemas import CheckDomainRequest, CompanyCreate, CompanyOut, CompanyUpdate

router = APIRouter(prefix="/api/companies", tags=["companies"])


def _serialize(company) -> dict:
    out = CompanyOut.model_validate(company).model_dump(mode="json")
    out["source_label"] = get_label(COMPANY_SOURCES, company.source)
    return out


def _audit_payload(company) -> dict:
    return {"name": company.name, "domain": company.domain, "source": company.source}


@router.get("")
async def list_companies(
    source: int | None = None,
    industry: str | None = None,
    funding_stage: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
    environment: int | None = Depends(current_environment_from_query),
    db: AsyncSession = Depends(get_db),
    # Caller needs the dropdown to attach a self-sourced lead to the right
    # company on the Sales Dashboard Add-Lead modal (RBAC narrow-widening).
    _user: AdminUser = Depends(require_internal_or_caller),
) -> dict:
    companies = await CompanyCRUD.list_all(
        db,
        source=source,
        industry=industry,
        funding_stage=funding_stage,
        q=q,
        limit=limit,
        offset=offset,
        environment=environment,
    )
    return ok([_serialize(c) for c in companies])


@router.get("/{company_id}")
async def get_company(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    company = await CompanyCRUD.get_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company not found")
    return ok(_serialize(company))


@router.post("/check-domain")
async def check_domain(
    payload: CheckDomainRequest,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    """Used by signup flow + Apollo sync — `{exists: bool, company_id: int|null}`."""
    company = await CompanyCRUD.get_by_domain(db, payload.domain)
    return ok({"exists": company is not None, "company_id": company.id if company else None})


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    # Caller may need to create a fresh company row when self-sourcing a
    # lead on the Sales Dashboard. Same narrow widening as list/get above.
    user: AdminUser = Depends(require_internal_or_caller),
) -> dict:
    if payload.domain and await CompanyCRUD.get_by_domain(db, payload.domain):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="company with this domain exists")
    company = await CompanyCRUD.create(db, **payload.model_dump())
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
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
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_growth_or_bdr),
) -> dict:
    company = await CompanyCRUD.get_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company not found")
    before = _audit_payload(company)
    company = await CompanyCRUD.update(db, company, **payload.model_dump(exclude_unset=True))
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="company",
        entity_id=company.id,
        action="update",
        before_json=before,
        after_json=_audit_payload(company),
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(company), message="company updated")


@router.post("/{company_id}/enrich")
async def enrich_company(
    company_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_growth_or_bdr),
) -> dict:
    """
    Stub — real enrichment (Apollo / Clearbit) lives in a future
    `services/companies/enrichment.py`. For now we mark `enriched_at = now()`
    so the UI can flag this row as "manually marked enriched".
    """
    company = await CompanyCRUD.get_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company not found")
    company = await CompanyCRUD.mark_enriched(db, company)
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="company",
        entity_id=company.id,
        action="enrich",
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(company), message="company enriched")


@router.delete("/{company_id}")
async def delete_company(
    company_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_admin),
) -> dict:
    company = await CompanyCRUD.get_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company not found")
    await CompanyCRUD.soft_delete(db, company)
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="company",
        entity_id=company.id,
        action="delete",
        ip_address=request.client.host if request.client else None,
    )
    return ok(message="company deleted")
