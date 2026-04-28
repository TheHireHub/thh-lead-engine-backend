"""Pydantic schemas for unsubscribes."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UnsubscribeCreate(BaseModel):
    email: EmailStr
    prospect_id: Optional[int] = None
    source_campaign_id: Optional[int] = None
    reason: Optional[str] = Field(default=None, max_length=255)


class UnsubscribeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    prospect_id: Optional[int]
    source_campaign_id: Optional[int]
    reason: Optional[str]
    unsubscribed_at: datetime
