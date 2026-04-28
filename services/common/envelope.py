"""
Standard response envelope helpers for THH Lead Engine.

Every route returns `{success, message, data, error}` per the architecture
rules. These helpers keep the shape consistent.
"""

from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    """Standard API response envelope."""

    success: bool
    message: str
    data: Optional[T] = None
    error: Optional[str] = None


def ok(data: Any = None, message: str = "ok") -> dict:
    return {"success": True, "message": message, "data": data, "error": None}


def fail(message: str, error: Optional[str] = None, data: Any = None) -> dict:
    return {"success": False, "message": message, "data": data, "error": error}
