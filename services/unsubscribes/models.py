"""SQLAlchemy model for unsubscribes (§7.14)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from database_connection.connection import Base


class Unsubscribe(Base):
    __tablename__ = "unsubscribes"
    __table_args__ = (
        UniqueConstraint("email", name="uk_unsubscribes_email"),
        Index("idx_unsubscribes_prospect_id", "prospect_id"),
        Index("idx_unsubscribes_source_campaign_id", "source_campaign_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    prospect_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("prospects.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    source_campaign_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("campaigns.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    unsubscribed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
