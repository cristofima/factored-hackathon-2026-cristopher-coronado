"""Ownership checks for Transaction service operations."""

from collections.abc import Callable

import pytest

from services import TransactionService


def test_owned_transactions_are_returned() -> None:
    service = TransactionService()

    assert service.get_transactions("1010", "local-customer")
    assert service.get_transactions_by_recipient_name(
        "1010",
        "ACME",
        "local-customer",
    )
    assert service.get_transactions_by_type(
        "1010",
        "local-customer",
        card_id="66666",
    )


@pytest.mark.parametrize(
    "operation",
    [
        lambda: TransactionService().get_transactions("1000", "local-customer"),
        lambda: TransactionService().get_transactions_by_recipient_name(
            "1020",
            "ACME",
            "local-customer",
        ),
        lambda: TransactionService().get_transactions_by_type(
            "1000",
            "local-customer",
            card_id="55555",
        ),
    ],
)
def test_foreign_account_transactions_are_denied(
    operation: Callable[[], object],
) -> None:
    with pytest.raises(PermissionError, match="authenticated customer"):
        operation()