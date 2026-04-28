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
    request_type: int = Field(default=0, ge=0, le=4)
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
