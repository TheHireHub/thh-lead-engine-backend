"""Landing pages-relevant enums."""

from services.common.enums import LANDING_VARIANT_STATUSES, get_label, get_value, reverse

LANDING_VARIANT_STATUSES_REVERSE = reverse(LANDING_VARIANT_STATUSES)

__all__ = ["LANDING_VARIANT_STATUSES", "LANDING_VARIANT_STATUSES_REVERSE", "get_label", "get_value"]
