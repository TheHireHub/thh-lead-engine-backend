"""SQLAlchemy 2.0 model for `admin_users` (Schema doc §7.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from database_connection.connection import Base


class AdminUser(Base):
    __tablename__ = "admin_users"
    __table_args__ = (
        Index("idx_admin_users_role", "role"),
        Index("idx_admin_users_thh_user_id", "thh_user_id"),
        Index("idx_admin_users_deleted_at", "deleted_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(BigInteger(), "mysql"), primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    role: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, comment="see services.common.enums.ADMIN_ROLES (§6.1)")
    thh_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="reserved for v2 federation with thh-backend JWT")
    daily_call_target: Mapped[int] = mapped_column(
        TINYINT(unsigned=True),
        nullable=False,
        default=80,
        server_default="80",
        comment="per-rep daily call target — drives Sales Dashboard '80 calls/day' chip",
    )
    avatar_color: Mapped[Optional[str]] = mapped_column(
        String(7),
        nullable=True,
        comment="stable hex (#RRGGBB) for avatar tile; NULL = derive client-side from user id",
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
    )
