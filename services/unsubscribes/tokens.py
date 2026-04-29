"""
HMAC unsubscribe tokens (Schema doc Arch-26).

DB-agnostic per CLAUDE.md "Services / integrations" rules.

Used in outbound emails as a one-click `https://...` unsubscribe link
(also referenced by the `List-Unsubscribe` header). Token = base64
url-safe-encoded `email|hex_hmac`. Verification is constant-time.

Env:
    UNSUBSCRIBE_TOKEN_SECRET   — HMAC key. Required for verification; if
                                  unset, every token verifies as invalid.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Optional


def _secret() -> Optional[bytes]:
    raw = os.getenv("UNSUBSCRIBE_TOKEN_SECRET")
    return raw.encode("utf-8") if raw else None


def make_token(email: str) -> str:
    """Encode `email|HMAC` as a URL-safe base64 string."""
    secret = _secret()
    if not secret:
        raise RuntimeError("UNSUBSCRIBE_TOKEN_SECRET not configured")
    sig = hmac.new(secret, email.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{email}|{sig}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def verify_token(token: str) -> Optional[str]:
    """
    Constant-time verify. Returns the email on success, None on failure.
    """
    secret = _secret()
    if not secret or not token:
        return None
    try:
        # restore base64 padding
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + pad).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if "|" not in raw:
        return None
    email, sig = raw.rsplit("|", 1)
    expected = hmac.new(secret, email.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    return email
