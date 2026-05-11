"""Pydantic schemas for candidate_outreach (proposed §7.26-§7.27).

Three boundaries:
1. Inbound webhook from HH-BE  → `IngestPayload` (X-Service-Token auth)
2. Admin status mutations       → `StatusUpdate`, `OutcomeUpdate` (cookie auth)
3. List/detail responses        → `OutreachOut`, `OutreachWithCandidatesOut`
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ─── Inbound (THH → LEADS) ──────────────────────────────────────────────

class IngestCandidatePayload(BaseModel):
    """One candidate inside an Initiate Outreach click."""

    thh_candidate_id: str = Field(min_length=1, max_length=64)
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    email: Optional[str] = Field(default=None, max_length=255)
    linkedin_url: Optional[str] = Field(default=None, max_length=500)


class IngestInitiator(BaseModel):
    """Recruiter who clicked the button on HH-FE."""

    thh_user_id: Optional[int] = None
    email: Optional[str] = Field(default=None, max_length=255)
    name: Optional[str] = Field(default=None, max_length=255)


class IngestPayload(BaseModel):
    """Full payload posted by HH-BE on every Initiate Outreach click.

    Cap candidates at 200 here as a defense-in-depth — HH-FE caps at 100.
    Anything larger almost certainly indicates a payload bug, not a real
    bulk action.
    """

    thh_job_id: int = Field(gt=0)
    thh_job_title: str = Field(min_length=1, max_length=255)
    # company_id=0 is allowed → "unknown company" sentinel, lands in
    # the Unattributed queue. Same for an "Unknown company" name —
    # better than rejecting the push entirely.
    thh_company_id: int = Field(ge=0)
    thh_company_name: str = Field(min_length=1, max_length=255)
    thh_company_domain: Optional[str] = Field(default=None, max_length=255)

    initiated_by: IngestInitiator
    initiated_at: datetime
    channel: int = Field(ge=0, le=2, description="see OUTREACH_CHANNELS §6.29")

    candidates: list[IngestCandidatePayload] = Field(min_length=1, max_length=200)

    # HH-BE-supplied idempotency key. If absent here we synthesise from
    # job_id + initiator + epoch_seconds in the route — but explicit is
    # better, so we encourage HH-BE to send it.
    dedup_key: Optional[str] = Field(default=None, max_length=64)

    # Optional status hint from HH-BE. None → default 0 ("initiated") on
    # create, no-op on duplicate dedup_key. Set to 1 ("engaged") on the
    # send-success leg so the same dedup_key advances the existing row
    # without needing a separate PATCH endpoint. See OUTREACH_STATUSES §6.30.
    status: Optional[int] = Field(default=None, ge=0, le=3)


# ─── Admin mutations (cookie auth) ──────────────────────────────────────

class StatusUpdate(BaseModel):
    """Admin clicks "Mark Engaged / Hired / Dropped"."""

    status: int = Field(ge=0, le=3, description="see OUTREACH_STATUSES §6.30")
    notes: Optional[str] = Field(default=None, max_length=2000)


class OutcomeUpdate(BaseModel):
    """Admin records per-candidate outcome inside an outreach event."""

    outcome: int = Field(ge=0, le=4, description="see CANDIDATE_OUTCOMES §6.31")


# ─── Responses ──────────────────────────────────────────────────────────

class OutreachCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thh_candidate_id: str
    first_name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    linkedin_url: Optional[str]
    outcome: Optional[int]
    outcome_label: Optional[str] = None
    outcome_at: Optional[datetime]
    outcome_updated_by_user_id: Optional[int]
    created_at: datetime


class OutreachOut(BaseModel):
    """List-row shape — no nested candidate array (cheap list query)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    prospect_id: Optional[int]
    prospect_company_job_id: Optional[int]
    thh_job_id: int
    thh_job_title: str
    thh_company_id: int
    thh_company_name: str
    thh_company_domain: Optional[str]
    initiated_by_thh_user_id: Optional[int]
    initiated_by_email: Optional[str]
    initiated_by_name: Optional[str]
    initiated_at: datetime
    channel: int
    channel_label: Optional[str] = None
    candidate_count: int
    status: int
    status_label: Optional[str] = None
    status_updated_at: Optional[datetime]
    status_updated_by_user_id: Optional[int]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class OutreachWithCandidatesOut(OutreachOut):
    """Detail shape — includes the per-candidate child rows."""

    candidates: list[OutreachCandidateOut] = []
