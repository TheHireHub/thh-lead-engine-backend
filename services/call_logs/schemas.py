"""Pydantic schemas for call_logs (powers Caller "Next" view, Schema doc §5.5)."""

from __future__ import annotations

from datetime import date as date_t, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CallLogCreate(BaseModel):
    """Inbound call-log payload. caller_user_id is set by the route from
    the authenticated user (not accepted from the client) — see §5.5."""

    prospect_id: int
    outcome: int = Field(ge=0, le=7, description="see CALL_OUTCOMES §6.26")
    callback_at: Optional[datetime] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _callback_at_required_for_call_back(self) -> "CallLogCreate":
        # outcome=2 is call_back per §6.26
        if self.outcome == 2 and self.callback_at is None:
            raise ValueError("callback_at is required when outcome=call_back")
        return self


class CallLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    prospect_id: int
    prospect_name: Optional[str] = None
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    caller_user_id: int
    outcome: int
    outcome_label: Optional[str] = None
    callback_at: Optional[datetime]
    notes: Optional[str]
    called_at: datetime


class SkipPayload(BaseModel):
    prospect_id: int


class NextProspectOut(BaseModel):
    """Shape returned by /api/call-logs/next-prospect — minimal payload for the UI."""
    prospect_id: int
    name: Optional[str]
    title: Optional[str]
    company_id: Optional[int]
    phone: Optional[str]
    email: Optional[str]
    last_touched_at: Optional[datetime]
    rnr_count: int


class DailyStatsOut(BaseModel):
    """
    Per-caller daily call statistics (powers the Sales Dashboard's KPI
    strip + per-rep cards). `by_outcome` keys mirror CALL_OUTCOMES §6.26
    labels exactly so FE doesn't need a second mapping table.

    `date_from`/`date_to` is the inclusive window the counters were summed
    over. When the FE asks for a single day both fields are the same; the
    legacy `date` field still echoes `date_to` for back-compat with any
    consumer that hasn't migrated to the range pair yet.
    """
    caller_user_id: int
    date: date_t = Field(description="alias for date_to — kept for back-compat")
    date_from: date_t
    date_to: date_t
    calls_today: int = Field(description="UNIQUE prospects dialled in [date_from, date_to]")
    queue_calls_today: int = Field(
        default=0,
        description=(
            "UNIQUE prospects on the rep's CURRENTLY-OWNED queue that received "
            "a call in [date_from, date_to], regardless of who logged the call. "
            "Surfaces activity inherited via reassign so KPI doesn't show 0 "
            "after a hand-off."
        ),
    )
    target: int = Field(description="caller's daily_call_target × number of days in range")
    in_queue: int = Field(description="prospects still eligible to call right now")
    by_outcome: dict[str, int] = Field(
        description=(
            "{rnr, not_interested, call_back, follow_up, demo_scheduled, "
            "demo_attended, demo_no_show, converted} per §6.26 — every key "
            "always present, missing outcomes report 0"
        )
    )


class QueueRow(BaseModel):
    """One row in the caller's eligible queue (prospect snapshot)."""
    prospect_id: int
    name: Optional[str]
    title: Optional[str]
    company_id: Optional[int]
    company_name: Optional[str] = None
    owner_user_id: Optional[int] = None
    phone: Optional[str]
    email: Optional[str]
    stage: int
    stage_label: Optional[str] = None
    last_outcome: Optional[int] = None
    last_outcome_label: Optional[str] = None
    last_touched_at: Optional[datetime]
    # Latest call_log.callback_at, only populated when the most recent call
    # is still an open call_back / demo_scheduled. Drives the "Follow-up
    # Time" column. Null when the rep hasn't set one — FE renders "—" in
    # that case (no overdue chip).
    next_callback_at: Optional[datetime] = None
    source_channel: Optional[int] = None
    source_channel_label: Optional[str] = None
    rnr_count: int


class QueueOut(BaseModel):
    caller_user_id: int
    date: date_t
    total: int
    rows: list[QueueRow]
