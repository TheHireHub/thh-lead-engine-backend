"""prospects.created_by_user_id — caller scope (assigned OR added-by-me)

Revision ID: b8d12f4a3e07
Revises: b9d4c8e72a16
Create Date: 2026-05-05 14:00:00.000000

Backs the Sales Dashboard caller-scope rule: a caller can see a prospect
when they OWN it (`owner_user_id`) OR ADDED it (`created_by_user_id`).
Without this column callers only saw leads explicitly assigned to them,
so a caller adding a lead via the dashboard had no way to see it on their
own queue without admin intervention. Nullable so system-driven inserts
(Apollo cron, signup webhooks) can leave the column empty.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8d12f4a3e07"
down_revision: Union[str, None] = "b9d4c8e72a16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "prospects",
        sa.Column(
            "created_by_user_id",
            sa.BigInteger(),
            nullable=True,
            comment="admin_users.id of the user who added this prospect; NULL for system inserts",
        ),
    )
    op.create_foreign_key(
        "fk_prospects_created_by_user_id",
        "prospects",
        "admin_users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
        onupdate="CASCADE",
    )
    op.create_index(
        "idx_prospects_created_by_user_id",
        "prospects",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_prospects_created_by_user_id", table_name="prospects")
    op.drop_constraint(
        "fk_prospects_created_by_user_id", "prospects", type_="foreignkey"
    )
    op.drop_column("prospects", "created_by_user_id")
