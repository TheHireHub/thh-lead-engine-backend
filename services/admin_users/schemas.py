"""Pydantic request/response schemas for admin_users."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    role: int = Field(ge=0, le=6, description="see ADMIN_ROLES §6.1")
    daily_call_target: Optional[int] = Field(default=None, ge=0, le=255)
    avatar_color: Optional[str] = Field(default=None, max_length=7, pattern=r"^#[0-9A-Fa-f]{6}$")


class AdminUserUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    role: Optional[int] = Field(default=None, ge=0, le=6)
    daily_call_target: Optional[int] = Field(default=None, ge=0, le=255)
    avatar_color: Optional[str] = Field(default=None, max_length=7, pattern=r"^#[0-9A-Fa-f]{6}$")


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # Output uses plain `str`, not `EmailStr`. Input is still validated as
    # EmailStr on AdminUserCreate / LoginRequest, so nothing reserved-TLD
    # gets in via the API. But once a row exists (e.g. seeded directly into
    # MySQL or imported from an upstream system that allows .local / .test),
    # rejecting it at *response*-validation time turns every list call into
    # a 500 with stripped CORS headers and is masked as a CORS error in the
    # browser. Trust DB content for outputs (BUG-001).
    email: str
    first_name: str
    last_name: Optional[str]
    role: int
    role_label: Optional[str] = None
    thh_user_id: Optional[int]
    daily_call_target: int
    avatar_color: Optional[str]
    last_login_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=255)
