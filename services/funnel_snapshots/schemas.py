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
    """
    Coarse-grained funnel KPIs over a date range (Schema doc §3).

    The three Phase-2 percentages — Cold→Curious, Curious→Trial(via
    first_job_created), Demo→Converted — match the KPI ownership table in
    Schema doc §3:
      Growth owns Cold→Curious
      Product/CSM owns Curious→Trial first_job
      Sales owns Demo→Converted

    Note: stage_totals_in_range sums per-day prospect_count (a smoothed
    "presence over the period") while milestone_counts is unique
    prospects. The percentages are directional, not strict cohort rates.
    """
    from_date: date
    to_date: date
    cold: int
    curious: int
    converted: int
    cold_to_curious_pct: float
    curious_to_converted_pct: float
    # Per Schema doc §3 KPI ownership: Curious → Trial via first_job_created
    curious_to_first_job_pct: float
    # Per Schema doc §3: Demo Booked → Converted (Sales-owned)
    demo_to_converted_pct: float
    # Milestone counts (independent timestamps fire in any order — §3)
    demo_booked: int
    first_job_created: int
    first_applicant_received: int
    registered: int
