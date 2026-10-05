"""Canonical customer lifecycle values; independent of authentication status."""
from __future__ import annotations

CUSTOMER_STATUSES = ("Active", "Inactive", "Suspended", "Closed")


def normalize_customer_status(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().casefold()
    for status in CUSTOMER_STATUSES:
        if normalized == status.casefold():
            return status
    raise ValueError("Unknown customer status")
