"""prospect_company_job_candidate_notes — append-only notes per candidate

Revision ID: a4f9c2e10b5d
Revises: e7b3c2a91d04
Create Date: 2026-04-30 12:00:00.000000

Backs the CSM "Add Note" UX on /csm. The existing `decision_notes` column
on `prospect_company_job_candidates` holds only the latest note (single
TEXT field), so saved notes were silently overwritten on the next save
and never displayed back to the user.

This migration adds a sibling append-only table:
  - one row per note (no in-place edits to history)
  - FK to the candidate (CASCADE — note vanishes with the candidate)
  - FK to the author admin_user (RESTRICT — preserve attribution)
  - soft-delete column (Arch-19) so deletes leave an audit trail

The legacy `decision_notes` column is left in place — it's still used by
the Change-Status-with-note flow on `PATCH /candidates/{id}/status` and
removing it would break that endpoint. Treat it as legacy; new note
content should be written through `POST /candidates/{id}/notes`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4f9c2e10b5d"
down_revision: Union[str, None] = "e7b3c2a91d04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prospect_company_job_candidate_notes",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "candidate_id",
            sa.BigInteger,
            sa.ForeignKey(
                "prospect_company_job_candidates.id",
                ondelete="CASCADE",
                onupdate="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.BigInteger,
            sa.ForeignKey(
                "admin_users.id",
                ondelete="RESTRICT",
                onupdate="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.current_timestamp(),
            server_onupdate=sa.func.current_timestamp(),
        ),
        sa.Index("idx_pcjcn_candidate_id", "candidate_id"),
        sa.Index("idx_pcjcn_created_by", "created_by_user_id"),
        sa.Index("idx_pcjcn_deleted_at", "deleted_at"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade() -> None:
    op.drop_table("prospect_company_job_candidate_notes")
