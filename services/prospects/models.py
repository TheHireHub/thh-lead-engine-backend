"""
SQLAlchemy models for the prospects domain.

Tables (Schema doc):
- §7.3  prospects
- §7.4  prospect_channels (junction)
- §7.5  prospect_stage_history
- §7.19 prospect_merge_log
- §7.20 prospect_merge_review_queue
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from database_connection.connection import Base


# -------------------------------------------------------------------- §7.3
class Prospect(Base):
    __tablename__ = "prospects"
    __table_args__ = (
        UniqueConstraint("linkedin_url", name="uk_prospects_linkedin_url"),
        UniqueConstraint("apollo_contact_id", name="uk_prospects_apollo_contact_id"),
        Index("idx_prospects_email", "email"),
        Index("idx_prospects_phone", "phone"),
        Index("idx_prospects_stage", "stage"),
        Index("idx_prospects_owner_user_id", "owner_user_id"),
        Index("idx_prospects_created_by_user_id", "created_by_user_id"),
        Index("idx_prospects_source_channel", "source_channel"),
        Index("idx_prospects_company_id", "company_id"),
        Index("idx_prospects_thh_user_id", "thh_user_id"),
        Index("idx_prospects_quality_score", "quality_score"),
        Index("idx_prospects_last_touched_at", "last_touched_at"),
        Index("idx_prospects_registered_at", "registered_at"),
        Index("idx_prospects_demo_booked_at", "demo_booked_at"),
        Index("idx_prospects_first_job_created_at", "first_job_created_at"),
        Index("idx_prospects_first_applicant_received_at", "first_applicant_received_at"),
        Index("idx_prospects_converted_at", "converted_at"),
        Index("idx_prospects_deleted_at", "deleted_at"),
        Index("ix_prospects_environment", "environment"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    stage: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0, comment="see FUNNEL_STAGES §6.2")
    heat_level: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0, comment="see HEAT_LEVELS §6.25")
    heat_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_score: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0, comment="ICP fit 0-10")
    source_channel: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=12, comment="see CHANNELS §6.3")
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    # Caller-scope rule (§5.5 BDR isolation): a caller sees a prospect when
    # they OWN it (`owner_user_id`) OR ADDED it (`created_by_user_id`).
    # NULL for system-driven inserts (Apollo cron, signup webhooks, etc).
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    apollo_contact_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    thh_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="reverse pointer into thh-backend.users")
    first_touched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_touched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    touch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Milestones (Schema doc §3 — independent timestamps, not stages)
    registered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    demo_booked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    first_job_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    first_applicant_received_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    jobs_created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    applicants_received_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rnr_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="auto-marks not_interested at 3")

    environment: Mapped[Optional[int]] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="0=stage, 1=prod, NULL=legacy (visible in both views)",
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
    )


# -------------------------------------------------------------------- §7.4
class ProspectChannel(Base):
    """Junction: which channels has each prospect been touched on, with counts."""

    __tablename__ = "prospect_channels"
    __table_args__ = (
        Index("idx_prospect_channels_channel", "channel"),
        Index("idx_prospect_channels_last_touched_at", "last_touched_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    prospect_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("prospects.id", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
    )
    channel: Mapped[int] = mapped_column(TINYINT(unsigned=True), primary_key=True, comment="see CHANNELS §6.3")
    first_touched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    last_touched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
    )
    touch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


# -------------------------------------------------------------------- §7.5
class ProspectStageHistory(Base):
    __tablename__ = "prospect_stage_history"
    __table_args__ = (
        Index("idx_psh_prospect_id", "prospect_id"),
        Index("idx_psh_changed_at", "changed_at"),
        Index("idx_psh_to_stage", "to_stage"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    prospect_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("prospects.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    from_stage: Mapped[Optional[int]] = mapped_column(TINYINT(unsigned=True), nullable=True, comment="NULL on first insert")
    to_stage: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    changed_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


# -------------------------------------------------------------------- §7.19
class ProspectMergeLog(Base):
    __tablename__ = "prospect_merge_log"
    __table_args__ = (
        Index("idx_pml_kept", "kept_prospect_id"),
        Index("idx_pml_merged_by", "merged_by_user_id"),
        Index("idx_pml_merged_at", "merged_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kept_prospect_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("prospects.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    merged_prospect_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="no FK — merged row may be hard-deleted")
    match_strategy: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, comment="see MERGE_MATCH_STRATEGIES §6.14")
    merged_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    snapshot_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    merged_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


# -------------------------------------------------------------------- §7.20
class ProspectMergeReviewQueue(Base):
    __tablename__ = "prospect_merge_review_queue"
    __table_args__ = (
        Index("idx_pmrq_status", "status"),
        Index("idx_pmrq_created_at", "created_at"),
        Index("idx_pmrq_prospect_a", "prospect_a_id"),
        Index("idx_pmrq_prospect_b", "prospect_b_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    prospect_a_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("prospects.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    prospect_b_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("prospects.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    match_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, comment="0.000 - 1.000")
    match_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
    reviewed_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
