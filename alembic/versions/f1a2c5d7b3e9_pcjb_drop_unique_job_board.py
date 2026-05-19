"""prospect_company_job_boards — drop UNIQUE(job, board) to allow re-posts

Revision ID: f1a2c5d7b3e9
Revises: b8d12f4a3e07
Create Date: 2026-05-12 18:00:00.000000

The CSM jobs board originally stored one row per (job, board) pair with a
UNIQUE constraint on `(prospect_company_job_id, board)`. After we added the
new `stopped` status (CSM Halt button), the team wants to re-post the SAME
board later — the unique constraint blocks that. Drop it so each posting
attempt becomes its own row; the latest row's status drives the chip on the
Performance table.

Data is preserved as-is. The model still indexes board + status separately
for fast lookup; we don't need a replacement index because per-job board
counts are small (~10 rows max per job).
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f1a2c5d7b3e9"
down_revision: Union[str, None] = "b8d12f4a3e07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MySQL refuses to drop a UNIQUE that's backing an FK index. The FK
    # prospect_company_job_boards.prospect_company_job_id -> prospect_company_jobs.id
    # relies on the leading column of `uk_pcjb_job_board` for its index.
    # Create a non-unique composite index FIRST, then drop the UNIQUE.
    op.create_index(
        "idx_pcjb_job_board",
        "prospect_company_job_boards",
        ["prospect_company_job_id", "board"],
        unique=False,
    )
    op.drop_constraint(
        "uk_pcjb_job_board",
        "prospect_company_job_boards",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uk_pcjb_job_board",
        "prospect_company_job_boards",
        ["prospect_company_job_id", "board"],
    )
    op.drop_index("idx_pcjb_job_board", "prospect_company_job_boards")
