"""Pydantic schemas for the jobs subsystem."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    company_id: int
    title: str = Field(min_length=1, max_length=255)
    department: Optional[str] = Field(default=None, max_length=100)
    seniority: int = Field(default=0, ge=0, le=7)
    location: Optional[str] = Field(default=None, max_length=255)
    employment_type: int = Field(default=0, ge=0, le=4)
    open_count: int = Field(default=1, ge=1)
    paid_status: int = Field(default=0, ge=0, le=2)
    confidentiality: int = Field(default=0, ge=0, le=1)
    no_linkedin_post: int = Field(default=0, ge=0, le=1)
    source: int = Field(default=0, ge=0, le=6)
    source_url: Optional[str] = None
    source_external_id: Optional[str] = None
    jd_url: Optional[str] = None
    posting_url: Optional[str] = Field(default=None, max_length=500)
    expectation_target: Optional[int] = Field(default=None, ge=1, le=9999)
    notes: Optional[str] = None


class JobUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    status: Optional[int] = Field(default=None, ge=0, le=4)
    paid_status: Optional[int] = Field(default=None, ge=0, le=2)
    confidentiality: Optional[int] = Field(default=None, ge=0, le=1)
    no_linkedin_post: Optional[int] = Field(default=None, ge=0, le=1)
    assigned_to_csm_user_id: Optional[int] = None
    posting_url: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    title: str
    department: Optional[str]
    seniority: int
    seniority_label: Optional[str] = None
    location: Optional[str]
    employment_type: int
    open_count: int
    paid_status: int
    paid_status_label: Optional[str] = None
    confidentiality: int
    confidentiality_label: Optional[str] = None
    no_linkedin_post: int
    status: int
    status_label: Optional[str] = None
    candidates_prepared: int
    posted_at: Optional[datetime]
    opened_at: Optional[datetime] = None
    expectation_target: Optional[int]
    at_risk_at: Optional[datetime]
    target_met_at: Optional[datetime]
    total_applicants: int
    assigned_to_csm_user_id: Optional[int]
    posting_url: Optional[str] = None
    source_url: Optional[str] = None
    source: int = 0
    source_label: Optional[str] = None
    source_external_id: Optional[str] = None
    jd_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class InboundJobBoardEvent(BaseModel):
    """Payload from HH-BE when a customer publishes a job on app.thehirehub.ai.

    Idempotent on (source=6 thh_product, source_external_id=str(thh_job_id))
    via the existing UNIQUE constraint. Re-pushes update mutable fields
    (paid_status, title, location, posting_url) without overwriting fields
    the LEADS team may have edited.
    """

    # Required for identity + idempotency.
    thh_job_id: int = Field(ge=1)
    dedup_key: str = Field(min_length=1, max_length=255)

    # Job content (everything optional — HH-BE may have partial data).
    title: Optional[str] = Field(default=None, max_length=255)
    job_code: Optional[str] = Field(default=None, max_length=64)
    location: Optional[str] = Field(default=None, max_length=255)
    total_positions: Optional[int] = Field(default=None, ge=1)
    posting_url: Optional[str] = Field(default=None, max_length=500)
    jd_url: Optional[str] = Field(default=None, max_length=500)
    published_at: Optional[datetime] = None

    # Company identity — used to find/create the LEADS companies row.
    thh_company_id: Optional[int] = Field(default=None, ge=1)
    company_name: Optional[str] = Field(default=None, max_length=255)
    company_domain: Optional[str] = Field(default=None, max_length=255)
    company_website: Optional[str] = Field(default=None, max_length=500)

    # Subscription + creator identity — drives paid_status and is_internal flag.
    subscription_status: Optional[str] = Field(default=None, max_length=32, description="active/trialing/past_due/cancelled/null")
    plan_code: Optional[str] = Field(default=None, max_length=64)
    creator_email: Optional[str] = Field(default=None, max_length=255)
    creator_thh_user_id: Optional[int] = Field(default=None, ge=1)
    is_internal: bool = Field(default=False, description="true when posted by THH staff for promo")


class JobDistributionRequest(BaseModel):
    """Payload for the CSM "Post a Job" form (Schema doc §5.6, Arch-40)."""

    boards: list[int] = Field(min_length=1, description="JOB_BOARDS §6.27 ints")
    expectation_target: int = Field(ge=1, description="total applicants across all boards")
    days_threshold: int = Field(ge=1, description="UI takes days; backend computes at_risk_at")


class CandidateMatchCreate(BaseModel):
    prospect_company_job_id: int
    thh_candidate_id: Optional[int] = None
    candidate_name: str = Field(max_length=255)
    candidate_title: Optional[str] = None
    candidate_linkedin_url: Optional[str] = None
    candidate_summary: Optional[str] = None
    match_score: Optional[float] = Field(default=None, ge=0, le=1)
    match_method: int = Field(default=0, ge=0, le=2)
    match_notes: Optional[str] = None


class CandidateStatusUpdate(BaseModel):
    status: int = Field(ge=0, le=5, description="see JOB_CANDIDATE_STATUSES §6.23")
    decision_notes: Optional[str] = None


class JobBoardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    prospect_company_job_id: int
    board: int
    board_label: Optional[str] = None
    status: int
    status_label: Optional[str] = None
    external_url: Optional[str]
    posted_at: Optional[datetime]
    removed_at: Optional[datetime]
    applicant_count: int
    notes: Optional[str]
    posted_by_user_id: Optional[int]
    created_at: datetime
    updated_at: datetime


class BoardMarkPostedPayload(BaseModel):
    external_url: Optional[str] = None


class BoardMarkFailedPayload(BaseModel):
    notes: Optional[str] = None


class ApplicantCountPayload(BaseModel):
    board: int = Field(ge=0, le=8, description="JOB_BOARDS §6.27")
    applicant_count: int = Field(ge=0)


class JobHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    prospect_company_job_id: int
    field_name: str
    from_value: Optional[str]
    to_value: Optional[str]
    reason: Optional[str]
    changed_by_user_id: Optional[int]
    changed_at: datetime


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    prospect_company_job_id: int
    thh_candidate_id: Optional[int]
    candidate_name: str
    candidate_title: Optional[str]
    candidate_linkedin_url: Optional[str]
    candidate_summary: Optional[str]
    match_score: Optional[float]
    match_method: int
    match_method_label: Optional[str] = None
    status: int
    status_label: Optional[str] = None
    presented_at: Optional[datetime]
    decided_at: Optional[datetime]
    decision_notes: Optional[str]
    prepared_by_user_id: int
    created_at: datetime
    updated_at: datetime


# ----------------------------- candidate notes (append-only)

class CandidateNoteCreate(BaseModel):
    body: str = Field(min_length=1)


class CandidateNoteUpdate(BaseModel):
    body: str = Field(min_length=1)


class CandidateNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    candidate_id: int
    body: str
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime
