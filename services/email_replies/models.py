"""SQLAlchemy model for email_replies (§7.13)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from database_connection.connection import Base


class EmailReply(Base):
    __tablename__ = "email_replies"
    __table_args__ = (
        Index("idx_er_prospect_id", "prospect_id"),
        Index("idx_er_campaign_id", "campaign_id"),
        Index("idx_er_classification", "classification"),
        Index("idx_er_received_at", "received_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("campaigns.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    prospect_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("prospects.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    raw_body: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    from_address: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="reply sender email; nullable for pre-existing rows",
    )
    classification: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, comment="see REPLY_CLASSIFICATIONS §6.8")
    classified_by: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0, comment="see REPLY_CLASSIFIED_BY §6.9")
    classifier_confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
