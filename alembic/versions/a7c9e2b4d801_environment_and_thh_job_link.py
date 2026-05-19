"""anchor tables: environment tag + admin pref + thh_job_id link

Revision ID: a7c9e2b4d801
Revises: f1a2c5d7b3e9
Create Date: 2026-05-19 00:00:00.000000

Two features in one migration (combined per plan so operators run one command):

1. Stage/Prod env separation. Tag every anchor table with a nullable
   `environment` TINYINT (0=stage, 1=prod, NULL=legacy/visible-in-both).
   Existing rows stay NULL so the LEADS team's current view is unchanged.
   `admin_users.preferred_environment` stores the per-user toggle.

2. Cross-platform JD fetch. Add `prospect_company_jobs.thh_job_id` so a
   CRM admin can link the row to its HH-BE job and pull JD + search-field
   data live (read-through; never cached in LEADS DB).

The migration is idempotent on MySQL — each ADD/DROP is guarded with an
`information_schema` check so re-running on a partially-migrated DB is
safe. This matches the pattern used in the HH-BE migration scripts.

Coolify env-var changes needed before redeploy (documented in the LEADS
plan, not actioned here): THH_BACKEND_STAGE_URL, THH_BACKEND_PROD_URL,
THH_BACKEND_SERVICE_TOKEN_STAGE/_PROD, THH_INCOMING_SERVICE_TOKEN_STAGE/_PROD.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a7c9e2b4d801"
down_revision: Union[str, None] = "f1a2c5d7b3e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables that gain a free-standing `environment` TINYINT NULL column.
# Child tables (call_logs, prospect_stage_history, etc.) inherit env via
# JOIN to their FK parent and do NOT need a column.
_ANCHOR_TABLES: tuple[str, ...] = (
    "prospects",
    "companies",
    "campaigns",
    "landing_pages",
    "prospect_company_jobs",
    "funnel_daily_snapshots",
    "webhook_deliveries",
)


# ---------------------------------------------------------------------------
# information_schema helpers — idempotent guards
# ---------------------------------------------------------------------------

def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).first()
    return row is not None


def _index_exists(table: str, index_name: str) -> bool:
    """True if a regular or unique index of this name exists on the table."""
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = :t AND index_name = :i"
        ),
        {"t": table, "i": index_name},
    ).first()
    return row is not None


def _unique_constraint_exists(table: str, constraint_name: str) -> bool:
    """True if a named UNIQUE constraint exists on the table.

    `information_schema.statistics` returns one row per index column and
    is reliable for INDEXes including the implicit UNIQUE-backing index,
    but the canonical source for *named UNIQUE constraints* is
    `table_constraints`. We check both so the migration is safe under
    either MySQL representation.
    """
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_schema = DATABASE() AND table_name = :t "
            "  AND constraint_name = :c AND constraint_type = 'UNIQUE'"
        ),
        {"t": table, "c": constraint_name},
    ).first()
    if row is not None:
        return True
    # Fallback: some MySQL versions surface only the index entry.
    return _index_exists(table, constraint_name)


def _add_env_column(table: str) -> None:
    if _column_exists(table, "environment"):
        return
    op.add_column(
        table,
        sa.Column(
            "environment",
            sa.SmallInteger(),
            nullable=True,
            comment="0=stage, 1=prod, NULL=legacy/visible-in-both-views",
        ),
    )


def _add_env_index(table: str) -> None:
    index_name = f"ix_{table}_environment"
    if _index_exists(table, index_name):
        return
    op.create_index(index_name, table, ["environment"], unique=False)


def _drop_env_column(table: str) -> None:
    if not _column_exists(table, "environment"):
        return
    op.drop_column(table, "environment")


def _drop_env_index(table: str) -> None:
    index_name = f"ix_{table}_environment"
    if not _index_exists(table, index_name):
        return
    op.drop_index(index_name, table_name=table)


# ---------------------------------------------------------------------------
# Upgrade / downgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # 1. Anchor `environment` columns + per-column indexes
    for table in _ANCHOR_TABLES:
        _add_env_column(table)
        _add_env_index(table)

    # 2. Admin per-user toggle persistence
    if not _column_exists("admin_users", "preferred_environment"):
        op.add_column(
            "admin_users",
            sa.Column(
                "preferred_environment",
                sa.SmallInteger(),
                nullable=True,
                comment="UI default for stage/prod filter pill; NULL=All",
            ),
        )

    # 3. LEADS row → HH-BE job linkage (Feature B)
    if not _column_exists("prospect_company_jobs", "thh_job_id"):
        op.add_column(
            "prospect_company_jobs",
            sa.Column(
                "thh_job_id",
                sa.Integer(),
                nullable=True,
                comment="HH-BE jobs.id; combined with environment to pick stage vs prod host",
            ),
        )
    if not _index_exists("prospect_company_jobs", "ix_pcj_thh_job_id"):
        op.create_index(
            "ix_pcj_thh_job_id",
            "prospect_company_jobs",
            ["thh_job_id"],
            unique=False,
        )

    # 4. Widen funnel snapshots UNIQUE to include environment so the same
    #    dimension can exist in both envs without collision.
    if _unique_constraint_exists("funnel_daily_snapshots", "uk_fds_dimension"):
        op.drop_constraint(
            "uk_fds_dimension",
            "funnel_daily_snapshots",
            type_="unique",
        )
    if not _unique_constraint_exists("funnel_daily_snapshots", "uk_fds_dimension_env"):
        op.create_unique_constraint(
            "uk_fds_dimension_env",
            "funnel_daily_snapshots",
            ["snapshot_date", "stage", "channel", "owner_user_id", "environment"],
        )


def downgrade() -> None:
    # Reverse #4
    if _unique_constraint_exists("funnel_daily_snapshots", "uk_fds_dimension_env"):
        op.drop_constraint(
            "uk_fds_dimension_env",
            "funnel_daily_snapshots",
            type_="unique",
        )
    if not _unique_constraint_exists("funnel_daily_snapshots", "uk_fds_dimension"):
        op.create_unique_constraint(
            "uk_fds_dimension",
            "funnel_daily_snapshots",
            ["snapshot_date", "stage", "channel", "owner_user_id"],
        )

    # Reverse #3
    if _index_exists("prospect_company_jobs", "ix_pcj_thh_job_id"):
        op.drop_index("ix_pcj_thh_job_id", table_name="prospect_company_jobs")
    if _column_exists("prospect_company_jobs", "thh_job_id"):
        op.drop_column("prospect_company_jobs", "thh_job_id")

    # Reverse #2
    if _column_exists("admin_users", "preferred_environment"):
        op.drop_column("admin_users", "preferred_environment")

    # Reverse #1
    for table in reversed(_ANCHOR_TABLES):
        _drop_env_index(table)
        _drop_env_column(table)
