"""Pydantic schemas for webhook deliveries."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class WebhookDeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    provider: int
    provider_label: Optional[str] = None
    external_event_id: str
    status: int
    status_label: Optional[str] = None
    error_message: Optional[str]
    received_at: datetime
    processed_at: Optional[datetime]
