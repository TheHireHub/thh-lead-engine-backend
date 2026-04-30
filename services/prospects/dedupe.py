"""
Dedupe priority chain for prospects (Schema doc Arch-6, locked).

Order of precedence (Prateek): LinkedIn URL > email > phone.

DB-agnostic except for the session it borrows — pure orchestration over
`ProspectCRUD` lookups. Lives in its own module per DEV_A_INSTRUCTIONS so
both routes and the Apollo sync worker import the same helper.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .crud import ProspectCRUD
from .models import Prospect


async def find_existing(
    db: AsyncSession,
    *,
    linkedin_url: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
) -> Optional[Prospect]:
    """
    Return the first existing prospect matched by the strongest identifier
    supplied. Used by:
    - `POST /api/prospects/` (manual create — 409 on hit)
    - `workers/tasks/apollo_sync.py` (upsert)
    - `services/signups/` OTP-verify upsert (Dev B)
    """
    if linkedin_url:
        existing = await ProspectCRUD.get_by_linkedin(db, linkedin_url)
        if existing:
            return existing
    if email:
        existing = await ProspectCRUD.get_by_email(db, email)
        if existing:
            return existing
    if phone:
        existing = await ProspectCRUD.get_by_phone(db, phone)
        if existing:
            return existing
    return None
