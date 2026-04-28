"""Pydantic schemas for call_logs (powers Caller "Next" view, Schema doc §5.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CallLogCreate(BaseModel):
    prospect_id: int
    caller_user_id: int
    outcome: int = Field(ge=0, le=4, description="see CALL_OUTCOMES §6.26")
    callback_at: Optional[datetime] = None
    notes: Optional[str] = None


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
