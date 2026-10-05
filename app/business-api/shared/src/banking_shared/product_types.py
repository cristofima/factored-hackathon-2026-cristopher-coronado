"""Canonical product labels and compatibility with the source dataset."""

from __future__ import annotations

import unicodedata

CREDIT_CARD = "Credit Card"
DEBIT_CARD = "Debit Card"

PRODUCT_TYPE_LABELS = {
    "Savings Account": "Cuenta Ahorro",
    "Checking Account": "Cuenta Corriente",
    "Investment": "Inversi\u00f3n",
    "Mortgage Loan": "Pr\u00e9stamo Hipotecario",
    "Personal Loan": "Pr\u00e9stamo Personal",
    "Insurance": "Seguro",
    CREDIT_CARD: "Tarjeta Cr\u00e9dito",
    DEBIT_CARD: "Tarjeta D\u00e9bito",
}


def _normalized_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.strip().casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


_CANONICAL_TYPES = {
    _normalized_key(label): canonical
    for canonical, legacy in PRODUCT_TYPE_LABELS.items()
    for label in (canonical, legacy)
}
_CANONICAL_TYPES[_normalized_key("Pr\u00e9stamo Persona")] = "Personal Loan"


def normalize_product_type(value: str) -> str:
    """Translate a known source label, rejecting unsupported product types."""
    try:
        return _CANONICAL_TYPES[_normalized_key(value)]
    except KeyError:
        raise ValueError(f"Unknown product_type: {value!r}") from None


ACCOUNT_PRODUCT_TYPES = ("Savings Account", "Checking Account")
CARD_PRODUCT_TYPES = (CREDIT_CARD, DEBIT_CARD)


def card_type(value: str) -> str:
    """Preserve the Account service's credit/debit response contract."""
    canonical = normalize_product_type(value)
    return {CREDIT_CARD: "credit", DEBIT_CARD: "debit"}.get(canonical, canonical)