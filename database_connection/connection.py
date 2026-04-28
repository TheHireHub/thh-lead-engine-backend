"""
Async SQLAlchemy 2.0 connection module for THH Lead Engine.

Mirrors the role of `database_connection/connection.py` in thh-backend:
this is the single, central place that exposes the database to every other
module. Service layers should never import a DB driver or build engines
themselves — they take an `AsyncSession` from `get_db` (FastAPI dependency).
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


def _build_database_url() -> str:
    """
    Build the async MySQL URL from environment variables.

    Uses aiomysql driver. The lead engine runs against a NEW MySQL database
    on the SAME server as thh-backend (logically separate, no shared tables).
    """
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DB", "thh_lead_engine")
    return f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"


DATABASE_URL = _build_database_url()

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """
    Single declarative base shared by every service's models.py.

    Every model in `services/<domain>/models.py` MUST subclass this `Base`
    so that `Base.metadata` knows about it (used by setup_database.py and
    Alembic autogenerate).
    """


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an `AsyncSession` per request.

    Usage in routes:
        from fastapi import Depends
        from sqlalchemy.ext.asyncio import AsyncSession
        from database_connection.connection import get_db

        @router.get("/foo")
        async def foo(db: AsyncSession = Depends(get_db)):
            ...

    Sessions are committed by CRUD methods (or rolled back on error).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


__all__ = ["Base", "engine", "AsyncSessionLocal", "get_db", "DATABASE_URL"]
