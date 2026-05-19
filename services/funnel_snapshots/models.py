"""SQLAlchemy model for funnel_daily_snapshots (§7.17)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Index, Integer, SmallInteger,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from database_connection.connection import Base


class FunnelDailySnapshot(Base):
    __tablename__ = "funnel_daily_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_date", "stage", "channel", "owner_user_id", "environment",
            name="uk_fds_dimension_env",
        ),
        Index("idx_fds_snapshot_date", "snapshot_date"),
        Index("idx_fds_stage", "stage"),
        Index("ix_funnel_daily_snapshots_environment", "environment"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    stage: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, comment="see FUNNEL_STAGES §6.2")
    channel: Mapped[Optional[int]] = mapped_column(TINYINT(unsigned=True), nullable=True, comment="NULL = all-channel rollup")
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    prospect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    environment: Mapped[Optional[int]] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="0=stage, 1=prod, NULL=legacy (visible in both views)",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
