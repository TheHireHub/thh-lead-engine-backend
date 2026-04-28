"""Pydantic schemas for audit_log."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor_user_id: Optional[int]
    entity_type: str
    entity_id: Optional[int]
    action: str
    before_json: Optional[dict]
    after_json: Optional[dict]
    ip_address: Optional[str]
    created_at: datetime
