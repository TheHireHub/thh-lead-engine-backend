"""Pydantic schemas for email_replies."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EmailReplyCreate(BaseModel):
    campaign_id: Optional[int] = None
    prospect_id: int
    raw_body: str
    subject: Optional[str] = Field(default=None, max_length=500)
    classification: int = Field(ge=0, le=1, description="0=positive, 1=negative")
    classified_by: int = Field(default=0, ge=0, le=2)
    classifier_confidence: Optional[float] = Field(default=None, ge=0, le=1)


class EmailReplyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    campaign_id: Optional[int]
    prospect_id: int
    raw_body: str
    subject: Optional[str]
    classification: int
    classification_label: Optional[str] = None
    classified_by: int
    classifier_confidence: Optional[float]
    received_at: datetime
