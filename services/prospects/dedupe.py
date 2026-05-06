"""
Dedupe chain for prospects (Schema doc Arch-6 v2, 2026-05-06).

A prospect = a person. Two records are the same person when LinkedIn URL
matches OR email matches. Phone is **NOT** a dedupe key: Apollo "Corporate
Phone" is a company-level switchboard shared by every colleague in the
company (e.g. one CSV had 106 rows sharing `+91 12467 19666`), so phone-
based dedupe collapses an entire company down to one prospect. Multiple
contacts per company is the normal case — phone collisions must not block
them.

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
    phone: Optional[str] = None,  # accepted for API compat; intentionally unused
) -> Optional[Prospect]:
    """
    Return the first existing prospect matched by a person-unique identifier
    (LinkedIn URL, then email). Phone is accepted in the signature so callers
    don't need to change, but is intentionally ignored — see module docstring.

    Used by:
    - `POST /api/prospects/` (manual create — 409 on hit)
    - `POST /api/prospects/import-csv` (skip-on-hit)
    - `workers/tasks/apollo_sync.py` (upsert)
    - `services/signups/` OTP-verify upsert (Dev B)
    """
    del phone  # see docstring
    if linkedin_url:
        existing = await ProspectCRUD.get_by_linkedin(db, linkedin_url)
        if existing:
            return existing
    if email:
        existing = await ProspectCRUD.get_by_email(db, email)
        if existing:
            return existing
    return None
