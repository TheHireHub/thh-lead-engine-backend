"""SQLAlchemy model for webhook_deliveries (§7.18)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON, BigInteger, DateTime, Index, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from database_connection.connection import Base


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        UniqueConstraint("provider", "external_event_id", name="uk_wd_provider_event"),
        Index("idx_wd_status", "status"),
        Index("idx_wd_received_at", "received_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, comment="see WEBHOOK_PROVIDERS §6.12")
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False, comment="provider-supplied event ID")
    signature: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0, comment="see WEBHOOK_STATUSES §6.13")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
