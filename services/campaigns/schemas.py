"""Pydantic schemas for campaigns."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    channel: int = Field(ge=0, le=12)
    description: Optional[str] = None
    audience_filter_json: Optional[dict] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    audience_filter_json: Optional[dict] = None


class CampaignStatusChange(BaseModel):
    status: int = Field(ge=0, le=4, description="see CAMPAIGN_STATUSES §6.5")


class CampaignAddProspects(BaseModel):
    prospect_ids: list[int] = Field(min_length=1)


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    channel: int
    channel_label: Optional[str] = None
    status: int
    status_label: Optional[str] = None
    description: Optional[str]
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime


class CampaignEventCreate(BaseModel):
    campaign_id: Optional[int] = None
    prospect_id: int
    event_type: int = Field(ge=0, le=17, description="see CAMPAIGN_EVENT_TYPES §6.7")
    payload_json: Optional[dict] = None
