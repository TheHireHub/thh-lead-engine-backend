"""Company-relevant enums (§6.4)."""

from services.common.enums import COMPANY_SOURCES, get_label, get_value, reverse

COMPANY_SOURCES_REVERSE = reverse(COMPANY_SOURCES)

__all__ = ["COMPANY_SOURCES", "COMPANY_SOURCES_REVERSE", "get_label", "get_value"]
