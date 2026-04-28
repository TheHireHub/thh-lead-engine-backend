"""Pydantic schemas for companies."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    domain: Optional[str] = Field(default=None, max_length=255)
    linkedin_url: Optional[str] = Field(default=None, max_length=500)
    industry: Optional[str] = Field(default=None, max_length=100)
    size: Optional[str] = Field(default=None, max_length=50)
    revenue_range: Optional[str] = Field(default=None, max_length=50)
    funding_stage: Optional[str] = Field(default=None, max_length=50)
    source: int = Field(default=1, ge=0, le=3, description="see COMPANY_SOURCES §6.4")


class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    domain: Optional[str] = Field(default=None, max_length=255)
    linkedin_url: Optional[str] = Field(default=None, max_length=500)
    industry: Optional[str] = Field(default=None, max_length=100)
    size: Optional[str] = Field(default=None, max_length=50)
    revenue_range: Optional[str] = Field(default=None, max_length=50)
    funding_stage: Optional[str] = Field(default=None, max_length=50)


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    domain: Optional[str]
    linkedin_url: Optional[str]
    industry: Optional[str]
    size: Optional[str]
    revenue_range: Optional[str]
    funding_stage: Optional[str]
    source: int
    source_label: Optional[str] = None
    enriched_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
