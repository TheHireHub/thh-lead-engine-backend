"""Pydantic schemas for signups."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupCreate(BaseModel):
    landing_page_id: Optional[int] = None
    email: EmailStr
    name: Optional[str] = Field(default=None, max_length=255)
    company_name: Optional[str] = Field(default=None, max_length=255)
    domain: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=30)
    request_type: int = Field(default=0, ge=0, le=5)
    visitor_id: Optional[str] = Field(default=None, max_length=64)
    payload_json: Optional[dict] = None


class SignupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    landing_page_id: Optional[int]
    prospect_id: Optional[int]
    email: str
    name: Optional[str]
    company_name: Optional[str]
    domain: Optional[str]
    phone: Optional[str]
    request_type: int
    request_type_label: Optional[str] = None
    visitor_id: Optional[str]
    otp_verified_at: Optional[datetime]
    created_at: datetime
    # Surfaced for HH-inbound rendering on the FE (stage chip, source meta,
    # touch counts). Other request_types may have a different shape.
    payload_json: Optional[dict] = None


class OtpVerifyPayload(BaseModel):
    otp_code: str = Field(min_length=4, max_length=12)


# Inbound lead event from HH-BE (docs/INBOUND_LEADS.md §5.1).
# One push per event_type fire-point in HH-BE signup flow. Service-token auth.
InboundEventType = str  # validated below; widening to Literal causes too much churn


class InboundLeadEvent(BaseModel):
    # Required for idempotency + bookkeeping.
    event_type: str = Field(min_length=1, max_length=64)
    dedup_key: str = Field(min_length=1, max_length=255, description="HH-BE supplied; uniquely identifies this event")
    event_occurred_at: datetime

    # Identity (at least one of email / thh_user_id required — validated in ingest).
    email: Optional[EmailStr] = None
    thh_user_id: Optional[int] = Field(default=None, ge=1)

    # Optional enrichment.
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=30)
    company_name: Optional[str] = Field(default=None, max_length=255)
    designation: Optional[str] = Field(default=None, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=255)
    thh_company_id: Optional[int] = Field(default=None, ge=1)
    signup_source: Optional[str] = Field(default=None, max_length=128)
    source_meta: Optional[dict] = None
    touch: Optional[dict] = None
    anonymous: bool = False  # set by HH-BE for calendly-anon path (synthetic email)
