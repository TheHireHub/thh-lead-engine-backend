"""SQLAlchemy models: landing_pages, landing_page_variants, landing_page_visits (§7.9-7.11)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON, BigInteger, DateTime, ForeignKey, Index, Integer, SmallInteger,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from database_connection.connection import Base


class LandingPage(Base):
    __tablename__ = "landing_pages"
    __table_args__ = (
        UniqueConstraint("slug", name="uk_landing_pages_slug"),
        Index("idx_lp_prospect_id", "prospect_id"),
        Index("idx_lp_company_id", "company_id"),
        Index("idx_lp_source_campaign_id", "source_campaign_id"),
        Index("idx_lp_deleted_at", "deleted_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    prospect_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("prospects.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    template_key: Mapped[str] = mapped_column(String(50), nullable=False, default="classic")
    source_campaign_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("campaigns.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    default_content_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    visit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_visit_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
    )


class LandingPageVariant(Base):
    __tablename__ = "landing_page_variants"
    __table_args__ = (
        UniqueConstraint("landing_page_id", "variant_key", name="uk_lpv_page_variant"),
        Index("idx_lpv_status", "status"),
        Index("idx_lpv_deleted_at", "deleted_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    landing_page_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("landing_pages.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    variant_key: Mapped[str] = mapped_column(String(50), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    weight: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=100, comment="weighted random; 0=disabled")
    status: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0, comment="see LANDING_VARIANT_STATUSES §6.24")
    visit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signup_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
    )


class LandingPageVisit(Base):
    __tablename__ = "landing_page_visits"
    __table_args__ = (
        Index("idx_lpv_landing_page_id", "landing_page_id"),
        Index("idx_lpv_variant_id", "landing_page_variant_id"),
        Index("idx_lpv_prospect_id", "prospect_id"),
        Index("idx_lpv_visitor_id", "visitor_id"),
        Index("idx_lpv_visited_at", "visited_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    landing_page_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("landing_pages.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    landing_page_variant_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("landing_page_variants.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    prospect_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("prospects.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    visitor_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="cookie-based stable ID")
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="sha256(ip + secret) — never raw IP")
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    referrer: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    utm_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_content: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_term: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    visited_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
