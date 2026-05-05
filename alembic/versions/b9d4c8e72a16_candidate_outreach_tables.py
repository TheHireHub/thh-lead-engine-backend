"""candidate_outreach + candidate_outreach_candidates tables

Revision ID: b9d4c8e72a16
Revises: a4f9c2e10b5d
Create Date: 2026-05-04 18:00:00.000000

Backs the new THH→LEADS push: when a recruiter clicks "Initiate Outreach"
on HH-FE, HH-BE forwards a summary to LEADS so CRM viewers see candidate
sourcing activity per company prospect, and admins can mutate status
(initiated → engaged → hired → dropped) plus per-candidate outcome.

Two tables, parent + child:
- candidate_outreach              one row per click
- candidate_outreach_candidates   one row per candidate inside the click

Idempotency: parent row carries `dedup_key` (UNIQUE) so HH-BE retries
during transient failures collapse to one row, not duplicates.

Soft delete (Arch-19) on the parent. Children CASCADE — no orphaned
candidate rows after a soft-delete + later hard-delete cleanup pass.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import SMALLINT, TINYINT


revision: str = "b9d4c8e72a16"
down_revision: Union[str, None] = "a4f9c2e10b5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_outreach",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        # Resolved on receive — NULL means "unattributed", lands in admin queue.
        sa.Column(
            "prospect_id",
            sa.BigInteger,
            sa.ForeignKey(
                "prospects.id", ondelete="SET NULL", onupdate="CASCADE",
                name="fk_co_prospect",
            ),
            nullable=True,
        ),
        sa.Column(
            "prospect_company_job_id",
            sa.BigInteger,
            sa.ForeignKey(
                "prospect_company_jobs.id", ondelete="SET NULL", onupdate="CASCADE",
                name="fk_co_pcj",
            ),
            nullable=True,
        ),
        # THH-side IDs — no FK because THH lives in a separate database.
        sa.Column("thh_job_id", sa.Integer, nullable=False),
        sa.Column("thh_job_title", sa.String(255), nullable=False),
        sa.Column("thh_company_id", sa.Integer, nullable=False),
        sa.Column("thh_company_name", sa.String(255), nullable=False),
        sa.Column("thh_company_domain", sa.String(255), nullable=True),
        sa.Column("initiated_by_thh_user_id", sa.Integer, nullable=True),
        sa.Column("initiated_by_email", sa.String(255), nullable=True),
        sa.Column("initiated_by_name", sa.String(255), nullable=True),
        sa.Column("initiated_at", sa.DateTime, nullable=False),
        sa.Column(
            "channel",
            TINYINT(unsigned=True),
            nullable=False,
            server_default="1",
            comment="see OUTREACH_CHANNELS proposed §6.29",
        ),
        sa.Column("candidate_count", SMALLINT(unsigned=True), nullable=False),
        sa.Column(
            "status",
            TINYINT(unsigned=True),
            nullable=False,
            server_default="0",
            comment="see OUTREACH_STATUSES proposed §6.30",
        ),
        sa.Column("status_updated_at", sa.DateTime, nullable=True),
        sa.Column(
            "status_updated_by_user_id",
            sa.BigInteger,
            sa.ForeignKey(
                "admin_users.id", ondelete="RESTRICT", onupdate="CASCADE",
                name="fk_co_status_updated_by",
            ),
            nullable=True,
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("dedup_key", sa.String(64), nullable=False),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            server_onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("dedup_key", name="uk_co_dedup_key"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_co_prospect_id", "candidate_outreach", ["prospect_id"])
    op.create_index("idx_co_thh_job_id", "candidate_outreach", ["thh_job_id"])
    op.create_index("idx_co_thh_company_id", "candidate_outreach", ["thh_company_id"])
    op.create_index("idx_co_status", "candidate_outreach", ["status"])
    op.create_index("idx_co_initiated_at", "candidate_outreach", ["initiated_at"])
    op.create_index("idx_co_deleted_at", "candidate_outreach", ["deleted_at"])
    op.create_index(
        "idx_co_prospect_initiated",
        "candidate_outreach",
        ["prospect_id", "initiated_at"],
    )

    op.create_table(
        "candidate_outreach_candidates",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "outreach_id",
            sa.BigInteger,
            sa.ForeignKey(
                "candidate_outreach.id", ondelete="CASCADE", onupdate="CASCADE",
                name="fk_coc_outreach",
            ),
            nullable=False,
        ),
        sa.Column("thh_candidate_id", sa.String(64), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("linkedin_url", sa.String(500), nullable=True),
        sa.Column(
            "outcome",
            TINYINT(unsigned=True),
            nullable=True,
            comment="see CANDIDATE_OUTCOMES proposed §6.31",
        ),
        sa.Column("outcome_at", sa.DateTime, nullable=True),
        sa.Column(
            "outcome_updated_by_user_id",
            sa.BigInteger,
            sa.ForeignKey(
                "admin_users.id", ondelete="RESTRICT", onupdate="CASCADE",
                name="fk_coc_outcome_updated_by",
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "outreach_id", "thh_candidate_id", name="uk_coc_event_candidate"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "idx_coc_outreach_id", "candidate_outreach_candidates", ["outreach_id"]
    )
    op.create_index(
        "idx_coc_thh_candidate_id",
        "candidate_outreach_candidates",
        ["thh_candidate_id"],
    )
    op.create_index(
        "idx_coc_outcome", "candidate_outreach_candidates", ["outcome"]
    )


def downgrade() -> None:
    op.drop_table("candidate_outreach_candidates")
    op.drop_table("candidate_outreach")
