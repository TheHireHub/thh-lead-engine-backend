"""FastAPI routes for the jobs subsystem (powers the CSM Board)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.common.envelope import ok

from .crud import JobCandidateCRUD, JobCRUD
from .enums import (
    JOB_CONFIDENTIALITY, JOB_PAID_STATUSES, JOB_SENIORITY, JOB_STATUSES, get_label,
)
from .schemas import (
    CandidateMatchCreate, JobCreate, JobDistributionRequest, JobOut, JobUpdate,
)

router = APIRouter(prefix="/api/prospect-company-jobs", tags=["prospect_company_jobs"])


def _serialize(j) -> dict:
    out = JobOut.model_validate(j).model_dump()
    out["seniority_label"] = get_label(JOB_SENIORITY, j.seniority)
    out["paid_status_label"] = get_label(JOB_PAID_STATUSES, j.paid_status)
    out["confidentiality_label"] = get_label(JOB_CONFIDENTIALITY, j.confidentiality)
    out["status_label"] = get_label(JOB_STATUSES, j.status)
    return out


@router.get("/by-company/{company_id}")
async def list_for_company(company_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    rows = await JobCRUD.list_for_company(db, company_id)
    return ok([_serialize(r) for r in rows])


@router.get("/at-risk")
async def at_risk_jobs(db: AsyncSession = Depends(get_db)) -> dict:
    """Powers the "Jobs at Risk" CSM view."""
    rows = await JobCRUD.list_at_risk(db)
    return ok([_serialize(r) for r in rows])


@router.get("/{job_id}")
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    job = await JobCRUD.get_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return ok(_serialize(job))


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_job(payload: JobCreate, db: AsyncSession = Depends(get_db)) -> dict:
    job = await JobCRUD.create(db, **payload.model_dump(exclude_none=True))
    return ok(_serialize(job), message="job created")


@router.patch("/{job_id}")
async def update_job(job_id: int, payload: JobUpdate, db: AsyncSession = Depends(get_db)) -> dict:
    job = await JobCRUD.get_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    job = await JobCRUD.update(db, job, **payload.model_dump(exclude_unset=True))
    return ok(_serialize(job), message="job updated")


@router.post("/{job_id}/distribute")
async def distribute_job(
    job_id: int, payload: JobDistributionRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """CSM "Post a Job" — Schema doc §5.6, Arch-40."""
    job = await JobCRUD.get_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    job = await JobCRUD.distribute(
        db, job,
        boards=payload.boards,
        expectation_target=payload.expectation_target,
        days_threshold=payload.days_threshold,
    )
    return ok(_serialize(job), message="job distributed")


@router.get("/{job_id}/candidates")
async def list_candidates(job_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    rows = await JobCandidateCRUD.list_for_job(db, job_id)
    return ok([{"id": r.id, "candidate_name": r.candidate_name, "match_score": float(r.match_score) if r.match_score else None,
                "status": r.status} for r in rows])


@router.post("/candidates", status_code=status.HTTP_201_CREATED)
async def create_candidate_match(
    payload: CandidateMatchCreate, prepared_by_user_id: int, db: AsyncSession = Depends(get_db)
) -> dict:
    # TODO: replace `prepared_by_user_id` with current-user dep once auth lands.
    row = await JobCandidateCRUD.create(
        db, **payload.model_dump(exclude_none=True), prepared_by_user_id=prepared_by_user_id
    )
    return ok({"id": row.id}, message="candidate match created")
