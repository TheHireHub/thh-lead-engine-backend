"""Webhook enums."""

from services.common.enums import (
    WEBHOOK_PROVIDERS, WEBHOOK_STATUSES, get_label, get_value, reverse,
)

WEBHOOK_PROVIDERS_REVERSE = reverse(WEBHOOK_PROVIDERS)
WEBHOOK_STATUSES_REVERSE = reverse(WEBHOOK_STATUSES)

__all__ = [
    "WEBHOOK_PROVIDERS", "WEBHOOK_PROVIDERS_REVERSE",
    "WEBHOOK_STATUSES", "WEBHOOK_STATUSES_REVERSE",
    "get_label", "get_value",
]
