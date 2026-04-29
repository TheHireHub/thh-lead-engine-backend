"""Pydantic schemas for call_logs (powers Caller "Next" view, Schema doc §5.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CallLogCreate(BaseModel):
    prospect_id: int
    caller_user_id: int
    outcome: int = Field(ge=0, le=4, description="see CALL_OUTCOMES §6.26")
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
