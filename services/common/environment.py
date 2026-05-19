"""Stage/Prod environment tag — shared across all anchor services.

The LEADS CRM stores data from both HH-BE stage and HH-BE prod in a single
database. Each anchor row (prospects, companies, campaigns, landing_pages,
prospect_company_jobs, funnel_daily_snapshots, webhook_deliveries) carries
an `environment` TINYINT column:

    0 (ENV_STAGE) — row originated from stage HH-BE
    1 (ENV_PROD)  — row originated from prod HH-BE
    NULL          — legacy row (created before this migration); shown in
                    both stage and prod views so historical data stays
                    visible to operators regardless of filter

The Sidebar toggle in the FE has three states: Stage / Prod / All. When a
specific env is selected, list endpoints filter `WHERE env=:e OR env IS NULL`
so legacy rows continue to surface. Setting the toggle to "All" omits the
query param and every endpoint returns everything.

Inbound rows from HH-BE pushes are tagged at insert time based on which
service token was presented (see `env_from_service_token` in
`admin_users.deps`).
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement


# ─── Constants ──────────────────────────────────────────────────────────────

ENV_STAGE: int = 0
ENV_PROD: int = 1

#: Type alias for any concrete env value (excludes NULL/All).
Environment = Literal[0, 1]


ALLOWED_ENV_VALUES: frozenset[int] = frozenset((ENV_STAGE, ENV_PROD))


# ─── FastAPI query dependency ───────────────────────────────────────────────

def current_environment_from_query(
    environment: Optional[int] = Query(
        default=None,
        ge=0,
        le=1,
        description=(
            "Filter results to stage (0) or prod (1). Omit (or pass None) "
            "to see everything including legacy NULL-tagged rows."
        ),
    ),
) -> Optional[int]:
    """Reusable dep — every list endpoint takes this and threads it into CRUD."""
    if environment is not None and environment not in ALLOWED_ENV_VALUES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"environment must be one of {sorted(ALLOWED_ENV_VALUES)} or omitted",
        )
    return environment


# ─── Query-builder helper ───────────────────────────────────────────────────

def env_filter_clause(
    column: ColumnElement, environment: Optional[int]
) -> Optional[ColumnElement]:
    """Build a `WHERE env=:e OR env IS NULL` clause.

    Returns None when `environment is None` so the caller can `if clause:
    stmt = stmt.where(clause)` cleanly. Legacy NULL rows are intentionally
    surfaced in both stage and prod views — per locked plan.
    """
    if environment is None:
        return None
    return or_(column == environment, column.is_(None))
