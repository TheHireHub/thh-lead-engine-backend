"""Call logs enums."""

from services.common.enums import CALL_OUTCOMES, get_label, get_value, reverse

CALL_OUTCOMES_REVERSE = reverse(CALL_OUTCOMES)

__all__ = ["CALL_OUTCOMES", "CALL_OUTCOMES_REVERSE", "get_label", "get_value"]
