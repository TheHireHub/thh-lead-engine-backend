"""Signups enums."""

from services.common.enums import SIGNUP_REQUEST_TYPES, get_label, get_value, reverse

SIGNUP_REQUEST_TYPES_REVERSE = reverse(SIGNUP_REQUEST_TYPES)

__all__ = ["SIGNUP_REQUEST_TYPES", "SIGNUP_REQUEST_TYPES_REVERSE", "get_label", "get_value"]
