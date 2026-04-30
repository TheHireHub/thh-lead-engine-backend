"""FastAPI routes for the jobs subsystem (powers the CSM Board)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.deps import require_csm, require_dashboard_read
from services.admin_users.models import AdminUser
from services.audit.crud import AuditLogCRUD
from services.common.envelope import ok

from .crud import (
    JobBoardCRUD,
    JobCandidateCRUD,
    JobCRUD,
    JobHistoryCRUD,
    group_by_company,
)
from .enums import (
    JOB_BOARD_POSTING_STATUSES,
    JOB_BOARDS,
    JOB_CANDIDATE_MATCH_METHODS,
    JOB_CANDIDATE_STATUSES,
    JOB_CONFIDENTIALITY,
    JOB_PAID_STATUSES,
    JOB_SENIORITY,
    JOB_STATUSES,
    get_label,
)
from .schemas import (
    ApplicantCountPayload,
    BoardMarkFailedPayload,
    BoardMarkPostedPayload,
    CandidateMatchCreate,
    CandidateOut,
    CandidateStatusUpdate,
    JobBoardOut,
    JobCreate,
    JobDistributionRequest,
    JobHistoryOut,
    JobOut,
    JobUpdate,
)

router = APIRouter(prefix="/api/prospect-company-jobs", tags=["prospect_company_jobs"])


# --------------------------------------------------------------- serializers

def _serialize_job(j) -> dict:
    out = JobOut.model_validate(j).model_dump()
    out["seniority_label"] = get_label(JOB_SENIORITY, j.seniority)
    out["paid_status_label"] = get_label(JOB_PAID_STATUSES, j.paid_status)
    out["confidentiality_label"] = get_label(JOB_CONFIDENTIALITY, j.confidentiality)
    out["status_label"] = get_label(JOB_STATUSES, j.status)
    return out


def _serialize_board(b) -> dict:
    out = JobBoardOut.model_validate(b).model_dump()
    out["board_label"] = get_label(JOB_BOARDS, b.board)
    out["status_label"] = get_label(JOB_BOARD_POSTING_STATUSES, b.status)
    return out


def _serialize_candidate(c) -> dict:
    out = CandidateOut.model_validate(c).model_dump()
    out["match_method_label"] = get_label(JOB_CANDIDATE_MATCH_METHODS, c.match_method)
    out["status_label"] = get_label(JOB_CANDIDATE_STATUSES, c.status)
    if c.match_score is not None:
        out["match_score"] = float(c.match_score)
    return out


# --------------------------------------------------------------- jobs (read)

@router.get("/")
async def list_jobs(
    company_id: Optional[int] = None,
    status: Optional[int] = Query(default=None, ge=0, le=4),
    paid_status: Optional[int] = Query(default=None, ge=0, le=2),
    confidentiality: Optional[int] = Query(default=None, ge=0, le=1),
    no_linkedin_post: Optional[int] = Query(default=None, ge=0, le=1),
    assigned_to_csm_user_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """Combined filter for the CSM Board. All params optional."""
    rows = await JobCRUD.list_filtered(
        db,
        company_id=company_id,
        status=status,
        paid_status=paid_status,
        confidentiality=confidentiality,
        no_linkedin_post=no_linkedin_post,
        assigned_to_csm_user_id=assigned_to_csm_user_id,
        limit=limit,
        offset=offset,
    )
    return ok([_serialize_job(r) for r in rows])


@router.get("/grouped-by-company")
async def grouped_by_company(
    status: Optional[int] = Query(default=None, ge=0, le=4),
    paid_status: Optional[int] = Query(default=None, ge=0, le=2),
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """For the design's company-grouped CSM view (Schema doc §5.4 / §5.2)."""
    rows = await JobCRUD.list_filtered(
        db, status=status, paid_status=paid_status, limit=1000
    )
    grouped = group_by_company(rows)
    out = [
        {
            "company_id": company_id,
            "jobs": [_serialize_job(j) for j in jobs],
            "count": len(jobs),
        }
        for company_id, jobs in grouped.items()
    ]
    return ok(out)


@router.get("/by-company/{company_id}")
async def list_for_company(company_id: int, db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    rows = await JobCRUD.list_for_company(db, company_id)
    return ok([_serialize_job(r) for r in rows])


@router.get("/at-risk")
async def at_risk_jobs(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """Powers the Jobs at Risk CSM view (Schema doc §5.6, Arch-41)."""
    rows = await JobCRUD.list_at_risk(db)
    return ok([_serialize_job(r) for r in rows])


@router.get("/{job_id}")
async def get_job(job_id: int, db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    job = await JobCRUD.get_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return ok(_serialize_job(job))


@router.get("/{job_id}/history")
async def job_history(
    job_id: int,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """Field-change audit for tracked fields (status, paid_status, confidentiality, ...)."""
    job = await JobCRUD.get_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    rows = await JobHistoryCRUD.list_for_job(db, job_id, limit=limit)
    return ok([JobHistoryOut.model_validate(r).model_dump() for r in rows])


@router.get("/{job_id}/posting-helper")
async def posting_helper(job_id: int, db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """
    Schema doc §5.7 (P3 PENDING).

    Returns the field set the CSM needs to copy-paste into external job
    boards. The full §5.7 list mirrors thh-backend's format_job_message();
    the data source is undecided (lead engine local vs live thh-backend
    pull). For now we surface the fields that exist on the job row.

    TODO: lock decision with Ishank and either:
      (a) add child tables for the missing fields (skills, language reqs,
          compensation, panelists, eval criteria) to this lead-engine repo, or
      (b) add a thh-backend integration call to fetch the live job by
          source_external_id.
    """
    job = await JobCRUD.get_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return ok(
        {
            "job": _serialize_job(job),
            "ready_to_copy": {
                "header": {
                    "company_id": job.company_id,
                    "title": job.title,
                },
                "job_information": {
                    "id": job.id,
                    "title": job.title,
                    "department": job.department,
                    "seniority": get_label(JOB_SENIORITY, job.seniority),
                    "location": job.location,
                    "open_count": job.open_count,
                    "status": get_label(JOB_STATUSES, job.status),
                },
                "jd_url": job.jd_url,
                "notes": job.notes,
            },
            "_pending_p3": True,
        },
        message="posting helper (P3 minimal — full field set TBD)",
    )


# --------------------------------------------------------------- jobs (write)

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_job(payload: JobCreate, db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_csm),
) -> dict:
    job = await JobCRUD.create(db, **payload.model_dump(exclude_none=True))
    await AuditLogCRUD.record(
        db,
        entity_type="prospect_company_job",
        entity_id=job.id,
        action="create",
        after_json={"title": job.title, "company_id": job.company_id},
    )
    return ok(_serialize_job(job), message="job created")


@router.patch("/{job_id}")
async def update_job(
    job_id: int,
    payload: JobUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_csm),
) -> dict:
    job = await JobCRUD.get_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return ok(_serialize_job(job), message="no changes")

    def _safe(v):
        if v is None or isinstance(v, (int, str, bool, float)):
            return v
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)

    before_snapshot = {k: _safe(getattr(job, k, None)) for k in changes}
    job = await JobCRUD.update_with_history(db, job, changes=changes)
    after_snapshot = {k: _safe(getattr(job, k, None)) for k in changes}
    await AuditLogCRUD.record(
        db,
        entity_type="prospect_company_job",
        entity_id=job.id,
        action="update",
        before_json=before_snapshot,
        after_json=after_snapshot,
    )
    return ok(_serialize_job(job), message="job updated")


@router.post("/{job_id}/distribute")
async def distribute_job(
    job_id: int,
    payload: JobDistributionRequest,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_csm),
) -> dict:
    """CSM "Post a Job" — Schema doc §5.6, Arch-40."""
    job = await JobCRUD.get_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    job = await JobCRUD.distribute(
        db,
        job,
        boards=payload.boards,
        expectation_target=payload.expectation_target,
        days_threshold=payload.days_threshold,
    )
    await AuditLogCRUD.record(
        db,
        entity_type="prospect_company_job",
        entity_id=job.id,
        action="distribute",
        after_json={
            "boards": payload.boards,
            "expectation_target": payload.expectation_target,
            "days_threshold": payload.days_threshold,
            "at_risk_at": job.at_risk_at.isoformat() if job.at_risk_at else None,
        },
    )
    return ok(_serialize_job(job), message="job distributed")


# --------------------------------------------------------------- per-board

@router.get("/{job_id}/boards")
async def list_boards(job_id: int, db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    rows = await JobBoardCRUD.list_for_job(db, job_id)
    return ok([_serialize_board(r) for r in rows])


@router.post("/boards/{board_row_id}/mark-posted")
async def mark_board_posted(
    board_row_id: int,
    payload: BoardMarkPostedPayload,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_csm),
) -> dict:
    row = await JobBoardCRUD.get_by_id(db, board_row_id)
    if not row:
        raise HTTPException(status_code=404, detail="board row not found")
    row = await JobBoardCRUD.mark_posted(db, row, external_url=payload.external_url)
    await JobHistoryCRUD.record(
        db,
        prospect_company_job_id=row.prospect_company_job_id,
        field_name=f"board[{get_label(JOB_BOARDS, row.board)}].status",
        from_value="pending",
        to_value="posted",
    )
    return ok(_serialize_board(row), message="board marked posted")


@router.post("/boards/{board_row_id}/mark-failed")
async def mark_board_failed(
    board_row_id: int,
    payload: BoardMarkFailedPayload,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_csm),
) -> dict:
    row = await JobBoardCRUD.get_by_id(db, board_row_id)
    if not row:
        raise HTTPException(status_code=404, detail="board row not found")
    row = await JobBoardCRUD.mark_failed(db, row, notes=payload.notes)
    await JobHistoryCRUD.record(
        db,
        prospect_company_job_id=row.prospect_company_job_id,
        field_name=f"board[{get_label(JOB_BOARDS, row.board)}].status",
        from_value="pending",
        to_value="failed",
        reason=payload.notes,
    )
    return ok(_serialize_board(row), message="board marked failed")


@router.post("/boards/{board_row_id}/mark-removed")
async def mark_board_removed(
    board_row_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_csm),
) -> dict:
    row = await JobBoardCRUD.get_by_id(db, board_row_id)
    if not row:
        raise HTTPException(status_code=404, detail="board row not found")
    prev = get_label(JOB_BOARD_POSTING_STATUSES, row.status)
    row = await JobBoardCRUD.mark_removed(db, row)
    await JobHistoryCRUD.record(
        db,
        prospect_company_job_id=row.prospect_company_job_id,
        field_name=f"board[{get_label(JOB_BOARDS, row.board)}].status",
        from_value=prev,
        to_value="removed",
    )
    return ok(_serialize_board(row), message="board marked removed")


@router.post("/{job_id}/applicants")
async def record_applicants(
    job_id: int,
    payload: ApplicantCountPayload,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_csm),
) -> dict:
    """
    Set the per-board applicant count and recompute total_applicants.
    Sets target_met_at once on the first time total >= expectation_target
    (Arch-41 one-way ratchet).
    """
    job = await JobCRUD.get_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    was_met = job.target_met_at is not None
    job = await JobCRUD.record_applicants(
        db, job, board=payload.board, applicant_count=payload.applicant_count
    )
    if not was_met and job.target_met_at is not None:
        await AuditLogCRUD.record(
            db,
            entity_type="prospect_company_job",
            entity_id=job.id,
            action="target_met",
            after_json={
                "target": job.expectation_target,
                "total_applicants": job.total_applicants,
            },
        )
    return ok(_serialize_job(job), message="applicants recorded")


# --------------------------------------------------------------- candidates

@router.get("/{job_id}/candidates")
async def list_candidates(job_id: int, db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    rows = await JobCandidateCRUD.list_for_job(db, job_id)
    return ok([_serialize_candidate(r) for r in rows])


@router.post("/candidates", status_code=status.HTTP_201_CREATED)
async def create_candidate_match(
    payload: CandidateMatchCreate,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_csm),
) -> dict:
    row = await JobCandidateCRUD.create(
        db,
        **payload.model_dump(exclude_none=True),
        prepared_by_user_id=user.id,
    )
    await AuditLogCRUD.record(
        db,
        entity_type="prospect_company_job_candidate",
        entity_id=row.id,
        action="create",
        actor_user_id=user.id,
        after_json={
            "candidate_name": payload.candidate_name,
            "job_id": payload.prospect_company_job_id,
        },
    )
    return ok(_serialize_candidate(row), message="candidate match created")


@router.patch("/candidates/{candidate_id}/status")
async def update_candidate_status(
    candidate_id: int,
    payload: CandidateStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_csm),
) -> dict:
    cand = await JobCandidateCRUD.get_by_id(db, candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="candidate not found")
    before_status = cand.status
    cand = await JobCandidateCRUD.update_status(
        db, cand, status=payload.status, decision_notes=payload.decision_notes
    )
    await AuditLogCRUD.record(
        db,
        entity_type="prospect_company_job_candidate",
        entity_id=cand.id,
        action="status_change",
        before_json={"status": before_status},
        after_json={"status": cand.status, "decision_notes": payload.decision_notes},
    )
    return ok(_serialize_candidate(cand), message="candidate status updated")


@router.delete("/candidates/{candidate_id}")
async def delete_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_csm),
) -> dict:
    cand = await JobCandidateCRUD.get_by_id(db, candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="candidate not found")
    await JobCandidateCRUD.soft_delete(db, cand)
    await AuditLogCRUD.record(
        db,
        entity_type="prospect_company_job_candidate",
        entity_id=cand.id,
        action="delete",
    )
    return ok(message="candidate deleted")
