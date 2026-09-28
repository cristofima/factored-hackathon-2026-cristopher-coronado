"""Ownership checks for Account service reads."""

from collections.abc import Callable

import pytest

from services import AccountService, CardService, UserService


def test_owned_account_resources_are_returned() -> None:
    account_service = AccountService()
    card_service = CardService()
    user_service = UserService()

    assert account_service.get_account_details("1010", "local-customer") is not None
    assert card_service.get_credit_cards("1010", "local-customer")
    assert user_service.get_accounts_by_user_name(
        "bob.user@contoso.com",
        "local-customer",
    )


@pytest.mark.parametrize(
    "operation",
    [
        lambda: AccountService().get_account_details("1000", "local-customer"),
        lambda: CardService().get_card_details("card-1020", "local-customer"),
        lambda: UserService().get_accounts_by_user_name(
            "alice.user@contoso.com",
            "local-customer",
        ),
    ],
)
def test_foreign_account_resources_are_denied(operation: Callable[[], object]) -> None:
    with pytest.raises(PermissionError, match="authenticated customer"):
        operation()