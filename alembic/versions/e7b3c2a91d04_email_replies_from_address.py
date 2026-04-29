"""email_replies.from_address — sender email column for inbox display

Revision ID: e7b3c2a91d04
Revises: c1a4e7d9f201
Create Date: 2026-04-29 21:00:00.000000

Adds nullable VARCHAR(255) `from_address` to email_replies (§7.13). The
column is nullable because pre-existing rows don't have a sender stored
(historical replies were captured before this column existed). New
inbound replies should populate it via EmailReplyCreate.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7b3c2a91d04"
down_revision: Union[str, None] = "c1a4e7d9f201"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "email_replies",
        sa.Column(
            "from_address",
            sa.String(length=255),
            nullable=True,
            comment="reply sender email; nullable for pre-existing rows",
        ),
    )


def downgrade() -> None:
    op.drop_column("email_replies", "from_address")
