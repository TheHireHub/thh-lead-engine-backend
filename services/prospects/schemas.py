"""Pydantic schemas for prospects."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ProspectCreate(BaseModel):
    linkedin_url: Optional[str] = Field(default=None, max_length=500)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    title: Optional[str] = Field(default=None, max_length=255)
    company_id: Optional[int] = None
    source_channel: int = Field(default=12, ge=0, le=12, description="see CHANNELS §6.3")
    apollo_contact_id: Optional[str] = Field(default=None, max_length=100)
    # Optional owner at create time — route validates the target is an
    # active caller (role=4) before persist. Caller-initiated creates
    # auto-route to themselves regardless of this field.
    owner_user_id: Optional[int] = None


class ProspectUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    title: Optional[str] = Field(default=None, max_length=255)
    company_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    quality_score: Optional[int] = Field(default=None, ge=0, le=10)
    # Identifier edits — route runs Arch-6 v2 dedupe (linkedin OR email)
    # against OTHER prospects before applying, so editing can't merge two
    # distinct people into one row by accident.
    linkedin_url: Optional[str] = Field(default=None, max_length=500)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    source_channel: Optional[int] = Field(default=None, ge=0, le=12)


class ProspectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    linkedin_url: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    title: Optional[str]
    company_id: Optional[int]
    stage: int
    stage_label: Optional[str] = None
    heat_level: int
    heat_score: int
    quality_score: int
    source_channel: int
    source_channel_label: Optional[str] = None
    owner_user_id: Optional[int]
    # Resolved server-side from `admin_users.first_name + last_name` so the
    # FE doesn't have to issue a second round-trip per row to label owners
    # on lists / detail (BUG-008). None when prospect is unowned.
    owner_name: Optional[str] = None
    apollo_contact_id: Optional[str]
    thh_user_id: Optional[int]
    first_touched_at: Optional[datetime]
    last_touched_at: Optional[datetime]
    touch_count: int
    registered_at: Optional[datetime]
    demo_booked_at: Optional[datetime]
    first_job_created_at: Optional[datetime]
    first_applicant_received_at: Optional[datetime]
    converted_at: Optional[datetime]
    jobs_created_count: int
    applicants_received_count: int
    rnr_count: int
    created_at: datetime
    updated_at: datetime


class StageChange(BaseModel):
    to_stage: int = Field(ge=0, le=4)
    reason: Optional[str] = Field(default=None, max_length=255)


class TouchRequest(BaseModel):
    channel: int = Field(ge=0, le=12, description="see CHANNELS §6.3")


class MergeDecision(BaseModel):
    decision: str = Field(pattern="^(merged|rejected)$")
    kept_prospect_id: Optional[int] = None
    merged_prospect_id: Optional[int] = None
