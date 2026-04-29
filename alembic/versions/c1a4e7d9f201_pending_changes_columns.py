"""pending_changes columns: admin_users.daily_call_target + avatar_color, prospect_company_jobs.posting_url

Revision ID: c1a4e7d9f201
Revises: 08085eaf24de
Create Date: 2026-04-29 19:00:00.000000

Backs the FE-driven additions tracked in BACKEND_CHANGES_PENDING.md:
  - item 6  : admin_users.daily_call_target — per-rep daily target (default 80)
  - item 9c : admin_users.avatar_color — stable hex tile colour
  - item 9a : prospect_company_jobs.posting_url — outreach destination URL
                (separate from jd_url which is the JD doc — see §7.21)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "c1a4e7d9f201"
down_revision: Union[str, None] = "08085eaf24de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # admin_users — daily_call_target + avatar_color
    op.add_column(
        "admin_users",
        sa.Column(
            "daily_call_target",
            mysql.TINYINT(unsigned=True),
            nullable=False,
            server_default="80",
            comment="per-rep daily call target — drives Sales Dashboard chip",
        ),
    )
    op.add_column(
        "admin_users",
        sa.Column(
            "avatar_color",
            sa.String(length=7),
            nullable=True,
            comment="stable hex (#RRGGBB) for avatar tile; NULL = derive client-side",
        ),
    )

    # prospect_company_jobs — posting_url
    op.add_column(
        "prospect_company_jobs",
        sa.Column(
            "posting_url",
            sa.String(length=500),
            nullable=True,
            comment="outreach destination URL; separate from jd_url (JD doc) per §7.21",
        ),
    )


def downgrade() -> None:
    op.drop_column("prospect_company_jobs", "posting_url")
    op.drop_column("admin_users", "avatar_color")
    op.drop_column("admin_users", "daily_call_target")
