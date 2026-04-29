"""Pydantic schemas for funnel snapshots."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    snapshot_date: date
    stage: int
    stage_label: Optional[str] = None
    channel: Optional[int]
    channel_label: Optional[str] = None
    owner_user_id: Optional[int]
    prospect_count: int
    created_at: datetime


SnapshotMode = Literal["daily", "weekly", "monthly"]


class AggregatedBucket(BaseModel):
    """A single bucket in a daily/weekly/monthly aggregation."""
    bucket_key: str  # e.g. '2026-04-01' (daily), '2026-W14' (weekly), '2026-04' (monthly)
    bucket_start: date
    stage: int
    stage_label: Optional[str] = None
    prospect_count: int


class TodayCountsOut(BaseModel):
    """Live counts from `prospects` grouped by stage (current value)."""
    stage_counts: dict[int, int]
    stage_labels: dict[int, str]
    total: int


class ConversionRatesOut(BaseModel):
    """Coarse-grained funnel KPIs over a date range (Schema doc §3)."""
    from_date: date
    to_date: date
    cold: int
    curious: int
    converted: int
    cold_to_curious_pct: float
    curious_to_converted_pct: float
    # Milestone-based rates (don't fit a single linear funnel — see §3)
    demo_booked: int
    first_job_created: int
    first_applicant_received: int
    registered: int
