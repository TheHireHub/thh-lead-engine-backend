"""Pydantic schemas for prospect_notes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class NoteCreate(BaseModel):
    prospect_id: int
    body: str = Field(min_length=1)
    assigned_to_user_id: Optional[int] = None
    due_date: Optional[date] = None
    status: int = Field(default=0, ge=0, le=2)


class NoteUpdate(BaseModel):
    body: Optional[str] = None
    assigned_to_user_id: Optional[int] = None
    due_date: Optional[date] = None
    status: Optional[int] = Field(default=None, ge=0, le=2)


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    prospect_id: int
    body: str
    assigned_to_user_id: Optional[int]
    due_date: Optional[date]
    status: int
    status_label: Optional[str] = None
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime
