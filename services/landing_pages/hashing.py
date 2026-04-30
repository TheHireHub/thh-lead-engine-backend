"""
Visitor IP hashing for landing-page visits.

Schema doc §7.11 + Arch-26: never store raw IPs. Instead store
sha256(ip + secret) using VISITOR_IP_HASH_SECRET so we can dedupe /
analyse without GDPR exposure.
"""

from __future__ import annotations

import hashlib
import os


_DEV_IP_HASH_DEFAULT = "dev-ip-hash-secret-change-me"


def hash_ip(ip: str | None) -> str | None:
    """Return sha256(ip + secret) hex digest, or None if no IP."""
    if not ip:
        return None
    secret = os.getenv("VISITOR_IP_HASH_SECRET", _DEV_IP_HASH_DEFAULT)
    if (os.getenv("APP_ENV", "development").lower() == "production") and (
        not secret or secret == _DEV_IP_HASH_DEFAULT or "change-me" in secret.lower()
    ):
        raise RuntimeError(
            "VISITOR_IP_HASH_SECRET must be set to a strong, non-default value in production"
        )
    return hashlib.sha256(f"{ip}:{secret}".encode("utf-8")).hexdigest()
