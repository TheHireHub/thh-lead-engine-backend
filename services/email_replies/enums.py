"""Email replies enums."""

from services.common.enums import (
    REPLY_CLASSIFICATIONS, REPLY_CLASSIFIED_BY, get_label, get_value, reverse,
)

REPLY_CLASSIFICATIONS_REVERSE = reverse(REPLY_CLASSIFICATIONS)
REPLY_CLASSIFIED_BY_REVERSE = reverse(REPLY_CLASSIFIED_BY)

__all__ = [
    "REPLY_CLASSIFICATIONS", "REPLY_CLASSIFICATIONS_REVERSE",
    "REPLY_CLASSIFIED_BY", "REPLY_CLASSIFIED_BY_REVERSE",
    "get_label", "get_value",
]
