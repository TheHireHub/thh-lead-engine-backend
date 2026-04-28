"""SQLAlchemy models: campaigns, campaign_prospects, campaign_events (§7.6-7.8)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON, BigInteger, DateTime, ForeignKey, Index, String, Text, func,
)
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from database_connection.connection import Base


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        Index("idx_campaigns_status", "status"),
        Index("idx_campaigns_channel", "channel"),
        Index("idx_campaigns_created_by", "created_by_user_id"),
        Index("idx_campaigns_deleted_at", "deleted_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, comment="see CHANNELS §6.3")
    status: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0, comment="see CAMPAIGN_STATUSES §6.5")
    audience_filter_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
    )


class CampaignProspect(Base):
    __tablename__ = "campaign_prospects"
    __table_args__ = (
        Index("idx_cp_prospect_id", "prospect_id"),
        Index("idx_cp_status", "status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    campaign_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("campaigns.id", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True
    )
    prospect_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("prospects.id", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True
    )
    status: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


class CampaignEvent(Base):
    __tablename__ = "campaign_events"
    __table_args__ = (
        Index("idx_ce_prospect_id", "prospect_id"),
        Index("idx_ce_campaign_id", "campaign_id"),
        Index("idx_ce_event_type", "event_type"),
        Index("idx_ce_occurred_at", "occurred_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("campaigns.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    prospect_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("prospects.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    event_type: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, comment="see CAMPAIGN_EVENT_TYPES §6.7")
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
