"""Pydantic schemas for landing pages, variants, visits."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LandingPageCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=255)
    prospect_id: Optional[int] = None
    company_id: Optional[int] = None
    template_key: str = Field(default="classic", max_length=50)
    source_campaign_id: Optional[int] = None
    default_content_json: Optional[dict] = None


class LandingPageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    prospect_id: Optional[int]
    company_id: Optional[int]
    template_key: str
    source_campaign_id: Optional[int]
    default_content_json: Optional[dict]
    visit_count: int
    last_visit_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class VariantCreate(BaseModel):
    landing_page_id: int
    variant_key: str = Field(max_length=50)
    content_json: dict
    weight: int = Field(default=100, ge=0, le=1000)
    status: int = Field(default=0, ge=0, le=2, description="see LANDING_VARIANT_STATUSES §6.24")


class VariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    landing_page_id: int
    variant_key: str
    content_json: dict
    weight: int
    status: int
    visit_count: int
    signup_count: int
    created_at: datetime
    updated_at: datetime


class VariantStatusUpdate(BaseModel):
    status: int = Field(ge=0, le=2)


class VariantPerformance(BaseModel):
    """Per-variant analytics for the performance endpoint."""
    id: int
    variant_key: str
    status: int
    weight: int
    visit_count: int
    signup_count: int
    signup_rate: float = Field(description="signup_count / visit_count, 0 if no visits")


class VisitCreate(BaseModel):
    landing_page_id: int
    landing_page_variant_id: Optional[int] = None
    visitor_id: str = Field(min_length=1, max_length=64)
    referrer: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None


class RenderOut(BaseModel):
    """Response shape for /by-slug/{slug}/render — what the public landing page consumes."""
    page: LandingPageOut
    picked_variant: Optional[VariantOut] = None
    content_json: dict = Field(
        description="The content to render — variant override or default_content_json fallback",
    )


class VisitsAggregateOut(BaseModel):
    """
    Visits aggregate over a date range, bucketed by marketing channel
    (Schema doc §3 Funnel KPI ownership; mapping in
    services/landing_pages/utm_mapping.py).

    `total` = all visits in the window.
    `by_source` keys = {"seo", "paid", "outreach"}.
    """
    from_date: date
    to_date: date
    total: int
    by_source: dict[str, int]
