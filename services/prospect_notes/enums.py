"""Prospect notes enums."""

from services.common.enums import NOTE_STATUSES, get_label, get_value, reverse

NOTE_STATUSES_REVERSE = reverse(NOTE_STATUSES)

__all__ = ["NOTE_STATUSES", "NOTE_STATUSES_REVERSE", "get_label", "get_value"]
