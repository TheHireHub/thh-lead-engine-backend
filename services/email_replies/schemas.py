"""Pydantic schemas for email_replies."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EmailReplyCreate(BaseModel):
    """Inbound reply payload. classification optional — rule classifier runs if absent."""

    campaign_id: Optional[int] = None
    prospect_id: int
    raw_body: str
    subject: Optional[str] = Field(default=None, max_length=500)
    classification: Optional[int] = Field(default=None, ge=0, le=1, description="see §6.8")
    classified_by: Optional[int] = Field(default=None, ge=0, le=2, description="see §6.9")
    classifier_confidence: Optional[float] = Field(default=None, ge=0, le=1)


class EmailReplyReclassify(BaseModel):
    """Manual override (sets classified_by=2 manual per §6.9)."""

    classification: int = Field(ge=0, le=1)


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
    classified_by_label: Optional[str] = None
    classifier_confidence: Optional[float]
    received_at: datetime
