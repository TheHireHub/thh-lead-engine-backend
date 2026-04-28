"""Pydantic schemas for funnel snapshots."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

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
