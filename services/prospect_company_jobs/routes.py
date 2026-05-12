"""FastAPI routes for the jobs subsystem (powers the CSM Board)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from database_connection.connection import get_db
from services.admin_users.deps import (
    ROLE_ADMIN,
    require_admin,
    require_csm,
    require_internal,
)
from services.admin_users.models import AdminUser
from services.audit.crud import AuditLogCRUD
from services.candidate_outreach.auth import require_service_token
from services.common.envelope import ok
from services.companies.crud import CompanyCRUD
from services.webhooks.crud import WebhookDeliveryCRUD

from .crud import (
    JobBoardCRUD,
    JobCandidateCRUD,
    JobCandidateNoteCRUD,
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
    CandidateNoteCreate,
    CandidateNoteOut,
    CandidateNoteUpdate,
    CandidateOut,
    CandidateStatusUpdate,
    InboundJobBoardEvent,
    JobBoardOut,
    JobCreate,
    JobDistributionRequest,
    JobHistoryOut,
    JobOut,
    JobUpdate,
)
from .models import ProspectCompanyJob

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

@router.get("")
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
    _user: AdminUser = Depends(require_internal),
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
    _user: AdminUser = Depends(require_internal),
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
    _user: AdminUser = Depends(require_internal),
) -> dict:
    rows = await JobCRUD.list_for_company(db, company_id)
    return ok([_serialize_job(r) for r in rows])


@router.get("/at-risk")
async def at_risk_jobs(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    """Powers the Jobs at Risk CSM view (Schema doc §5.6, Arch-41)."""
    rows = await JobCRUD.list_at_risk(db)
    return ok([_serialize_job(r) for r in rows])


@router.get("/{job_id}")
async def get_job(job_id: int, db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    job = await JobCRUD.get_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return ok(_serialize_job(job))


@router.get("/{job_id}/detail")
async def get_job_detail(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    """Rich view used by the CSM Board drawer.

    Joins the job row with its company, all board posting rows, recent history,
    and resolves admin user IDs (created_by, assigned_csm, board posters,
    history changers) to display names so the FE renders 'posted by <name>'
    without a second roundtrip per id.
    """
    from services.admin_users.crud import AdminUserCRUD
    from services.companies.models import Company

    job = await JobCRUD.get_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    boards = await JobBoardCRUD.list_for_job(db, job_id)
    history = await JobHistoryCRUD.list_for_job(db, job_id, limit=50)

    company = None
    if job.company_id:
        result = await db.execute(select(Company).where(Company.id == job.company_id))
        company = result.scalar_one_or_none()

    # Resolve admin names in one round-trip.
    user_ids: set[int] = set()
    if job.created_by_user_id:
        user_ids.add(job.created_by_user_id)
    if job.assigned_to_csm_user_id:
        user_ids.add(job.assigned_to_csm_user_id)
    for b in boards:
        if b.posted_by_user_id:
            user_ids.add(b.posted_by_user_id)
    for h in history:
        if h.changed_by_user_id:
            user_ids.add(h.changed_by_user_id)
    names_map = await AdminUserCRUD.names_by_ids(db, list(user_ids)) if user_ids else {}

    def _board_dict(b) -> dict:
        d = _serialize_board(b)
        d["posted_by_name"] = names_map.get(b.posted_by_user_id) if b.posted_by_user_id else None
        return d

    def _history_dict(h) -> dict:
        d = JobHistoryOut.model_validate(h).model_dump()
        d["changed_by_name"] = names_map.get(h.changed_by_user_id) if h.changed_by_user_id else None
        return d

    return ok(
        {
            "job": _serialize_job(job),
            "company": (
                {
                    "id": company.id,
                    "name": company.name,
                    "domain": company.domain,
                    "linkedin_url": company.linkedin_url,
                    "industry": company.industry,
                    "size": company.size,
                }
                if company
                else None
            ),
            "boards": [_board_dict(b) for b in boards],
            "history": [_history_dict(h) for h in history],
            "created_by_name": names_map.get(job.created_by_user_id) if job.created_by_user_id else None,
            "assigned_to_csm_name": (
                names_map.get(job.assigned_to_csm_user_id) if job.assigned_to_csm_user_id else None
            ),
        }
    )


@router.get("/{job_id}/history")
async def job_history(
    job_id: int,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    """Field-change audit for tracked fields (status, paid_status, confidentiality, ...)."""
    job = await JobCRUD.get_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    rows = await JobHistoryCRUD.list_for_job(db, job_id, limit=limit)
    return ok([JobHistoryOut.model_validate(r).model_dump() for r in rows])


@router.get("/{job_id}/posting-helper")
async def posting_helper(job_id: int, db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
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

@router.post("", status_code=status.HTTP_201_CREATED)
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


# ----------------------------------------------------- inbound (HH product)

_JOB_SOURCE_THH_PRODUCT = 6           # JOB_SOURCES §6.20
_WEBHOOK_PROVIDER_THH_JOB_BOARD = 5   # WEBHOOK_PROVIDERS §6.12 (distinct from 4=thh_signup)
_PAID_STATUS_PAID = 1                 # JOB_PAID_STATUSES §6.18
_PAID_STATUS_NON_PAID = 2

_PAID_SUB_STATUSES = {"active", "past_due"}
_TRIAL_SUB_STATUSES = {"trialing", "trial"}


def _resolve_paid_status(subscription_status: Optional[str]) -> int:
    """Map a HH-BE subscription status string into the LEADS paid_status enum.

    Defines what "paid customer" means for CSM prioritisation on the board:
      active / past_due  -> paid (1)
      everything else    -> non_paid (2)
        - trialing / trial: free trial period, not yet revenue
        - cancelled: revenue stopped
        - null / unknown / anything weird: assume free until proven otherwise

    past_due IS counted as paid because the invoice is overdue (not cancelled);
    they're still a paying customer with a billing issue, sales should keep
    them in the paid bucket so CSM follows up. If product wants past_due to
    appear as "at risk" elsewhere we surface that via a separate signal, not
    by demoting paid_status here.
    """
    if not subscription_status:
        return _PAID_STATUS_NON_PAID
    return _PAID_STATUS_PAID if subscription_status.strip().lower() in _PAID_SUB_STATUSES else _PAID_STATUS_NON_PAID


def _extract_domain(url_or_domain: Optional[str]) -> Optional[str]:
    if not url_or_domain:
        return None
    raw = url_or_domain.strip().lower()
    if not raw:
        return None
    if "@" in raw and "://" not in raw:
        raw = raw.split("@", 1)[1]
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if raw.startswith("www."):
        raw = raw[4:]
    return raw or None


@router.post("/inbound")
async def inbound_job_board_event(
    payload: InboundJobBoardEvent,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
) -> dict:
    """HH-BE posts here when a customer publishes a job on app.thehirehub.ai.

    Idempotent on (source=6 thh_product, source_external_id=str(thh_job_id))
    AND on (provider=4 thh_signup, external_event_id=dedup_key). The first
    push creates the row; later pushes patch mutable fields (paid_status,
    posting_url, location, title) without touching CSM-curated fields
    (assigned_to_csm_user_id, expectation_target, notes, status).
    """
    # 1) Idempotency check via webhook_deliveries.
    wd_row, was_duplicate = await WebhookDeliveryCRUD.record(
        db,
        provider=_WEBHOOK_PROVIDER_THH_JOB_BOARD,
        external_event_id=payload.dedup_key,
        payload_json=payload.model_dump(mode="json"),
    )
    if was_duplicate:
        return ok(
            {"created": False, "job_id": None, "dedup_key": payload.dedup_key},
            message="already_received",
        )

    try:
        # 2) Resolve the LEADS company. HH posts always carry SOME identity
        # (company_name + domain or website). If neither resolves, bail —
        # ProspectCompanyJob.company_id is NOT NULL.
        domain = _extract_domain(payload.company_domain) or _extract_domain(payload.company_website)
        if not domain and not payload.company_name:
            await WebhookDeliveryCRUD.mark_failed(db, wd_row, "no company identity in payload")
            raise HTTPException(status_code=400, detail="company identity required")

        company = None
        if domain:
            company, _created = await CompanyCRUD.get_or_create_by_domain(
                db,
                domain=domain,
                name=payload.company_name or domain,
                source=2,  # COMPANY_SOURCES §6.4 = signup
            )

        if company is None:
            # No domain — anonymous internal promo? Use company_name as the
            # display name with a synthetic domain so the FK resolves. Anchor
            # on thh_company_id when available so all jobs from the same
            # company collapse into one LEADS company row; fall back to
            # job_id for unattributed posts. dedup_key is the ultimate
            # tiebreaker — used here only to avoid `None` ever appearing in
            # the synthetic-domain string.
            anchor = (
                payload.thh_company_id
                or payload.thh_job_id
                or f"k{abs(hash(payload.dedup_key)) % 10**9}"
            )
            synthetic_domain = f"thh-internal+{anchor}.local"
            company, _ = await CompanyCRUD.get_or_create_by_domain(
                db,
                domain=synthetic_domain,
                name=payload.company_name or "Internal promo",
                source=2,
            )

        # 3) Upsert on (source, source_external_id) UNIQUE.
        existing_result = await db.execute(
            select(ProspectCompanyJob).where(
                ProspectCompanyJob.source == _JOB_SOURCE_THH_PRODUCT,
                ProspectCompanyJob.source_external_id == str(payload.thh_job_id),
                ProspectCompanyJob.deleted_at.is_(None),
            )
        )
        job = existing_result.scalar_one_or_none()

        paid_status = _resolve_paid_status(payload.subscription_status)

        if job is None:
            job_fields = {
                "company_id": company.id,
                "title": (payload.title or payload.job_code or "Untitled job")[:255],
                "location": payload.location,
                "open_count": payload.total_positions or 1,
                "paid_status": paid_status,
                "source": _JOB_SOURCE_THH_PRODUCT,
                "source_url": payload.posting_url,
                "source_external_id": str(payload.thh_job_id),
                "posting_url": payload.posting_url,
                "jd_url": payload.jd_url,
                "posted_at": payload.published_at,
                "status": 0,  # open
            }
            job = await JobCRUD.create(db, **job_fields)
            await AuditLogCRUD.record(
                db,
                entity_type="prospect_company_job",
                entity_id=job.id,
                action="inbound_create",
                after_json={
                    "source": _JOB_SOURCE_THH_PRODUCT,
                    "source_external_id": str(payload.thh_job_id),
                    "is_internal": payload.is_internal,
                    "plan_code": payload.plan_code,
                    "subscription_status": payload.subscription_status,
                },
            )
            created = True
        else:
            # Patch mutable fields. Never overwrite CSM-curated columns.
            patch: dict = {}
            if payload.title and not job.title.startswith("Untitled"):
                # Keep CSM-edited title; only fill if it's still our default.
                pass
            elif payload.title:
                patch["title"] = payload.title[:255]
            if payload.location and not job.location:
                patch["location"] = payload.location
            if payload.posting_url and not job.posting_url:
                patch["posting_url"] = payload.posting_url
            if payload.jd_url and not job.jd_url:
                patch["jd_url"] = payload.jd_url
            if paid_status != job.paid_status:
                patch["paid_status"] = paid_status
            if payload.published_at and not job.posted_at:
                patch["posted_at"] = payload.published_at
            if patch:
                job = await JobCRUD.update(db, job, **patch)
                await AuditLogCRUD.record(
                    db,
                    entity_type="prospect_company_job",
                    entity_id=job.id,
                    action="inbound_update",
                    after_json=patch,
                )
            created = False

        await WebhookDeliveryCRUD.mark_processed(db, wd_row)
        return ok(
            {
                "created": created,
                "job_id": job.id,
                "company_id": company.id,
                "paid_status": paid_status,
                "dedup_key": payload.dedup_key,
            },
            message="ingested",
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        await WebhookDeliveryCRUD.mark_failed(db, wd_row, str(exc)[:1000])
        raise HTTPException(status_code=500, detail=f"ingest failed: {exc}")


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
    _user: AdminUser = Depends(require_internal),
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
    _user: AdminUser = Depends(require_internal),
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


# --------------------------------------------------------------- candidate notes
#
# Append-only notes per candidate. The legacy `decision_notes` TEXT column
# on the candidate is still used by Change-Status flows but is overwritten
# on each save; this is the surface for note history that the UI reads.

def _serialize_candidate_note(n) -> dict:
    return CandidateNoteOut.model_validate(n).model_dump(mode="json")


@router.get("/candidates/{candidate_id}/notes")
async def list_candidate_notes(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    cand = await JobCandidateCRUD.get_by_id(db, candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="candidate not found")
    rows = await JobCandidateNoteCRUD.list_for_candidate(db, candidate_id)
    return ok([_serialize_candidate_note(r) for r in rows])


@router.post(
    "/candidates/{candidate_id}/notes",
    status_code=status.HTTP_201_CREATED,
)
async def create_candidate_note(
    candidate_id: int,
    payload: CandidateNoteCreate,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_csm),
) -> dict:
    cand = await JobCandidateCRUD.get_by_id(db, candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="candidate not found")
    note = await JobCandidateNoteCRUD.create(
        db,
        candidate_id=candidate_id,
        body=payload.body,
        created_by_user_id=user.id,
    )
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="prospect_company_job_candidate_note",
        entity_id=note.id,
        action="create",
        after_json={"candidate_id": candidate_id},
    )
    return ok(_serialize_candidate_note(note), message="note added")


@router.patch("/candidates/notes/{note_id}")
async def update_candidate_note(
    note_id: int,
    payload: CandidateNoteUpdate,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_csm),
) -> dict:
    note = await JobCandidateNoteCRUD.get_by_id(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="note not found")
    # Authors can edit their own; admins can edit any.
    if note.created_by_user_id != user.id and user.role != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="cannot edit another user's note",
        )
    note = await JobCandidateNoteCRUD.update_body(db, note, body=payload.body)
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="prospect_company_job_candidate_note",
        entity_id=note.id,
        action="update",
    )
    return ok(_serialize_candidate_note(note), message="note updated")


@router.delete("/candidates/notes/{note_id}")
async def delete_candidate_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_admin),
) -> dict:
    note = await JobCandidateNoteCRUD.get_by_id(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="note not found")
    await JobCandidateNoteCRUD.soft_delete(db, note)
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="prospect_company_job_candidate_note",
        entity_id=note_id,
        action="delete",
    )
    return ok(message="note deleted")
