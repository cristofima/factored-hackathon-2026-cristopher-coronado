import pytest

from banking_account.services.products import _masked_card_number


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("4111111111111234", "4111 **** **** 1234"),
        ("4111-1111 1111-1234", "4111 **** **** 1234"),
        ("4111 **** **** 1234", "4111 **** **** 1234"),
        ("**** 1234", "**** 1234"),
        (None, None),
        ("", None),
        ("41111234", None),
        ("4111text1234", None),
        ("４１１１１１１１１１１１１２３４", None),
        ("41111111111111111234", None),
    ],
)
def test_card_number_exposes_only_known_edge_digits(
    number: str | None, expected: str | None
) -> None:
    assert _masked_card_number(number) == expected
