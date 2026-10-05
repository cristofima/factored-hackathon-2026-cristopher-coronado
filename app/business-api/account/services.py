from __future__ import annotations

import logging
import re
from collections.abc import Callable
from decimal import Decimal

from banking_shared.database import create_session
from banking_shared.models import Customer, Product
from banking_shared.runtime import project_runtime
from banking_shared.product_types import (
    ACCOUNT_PRODUCT_TYPES,
    CARD_PRODUCT_TYPES,
    card_type,
    normalize_product_type,
)
from models import (
    Account,
    AccountSummary,
    Beneficiary,
    Card,
    CardDiscoveryCandidate,
    CardDiscoveryResult,
    CardSummary,
    PaymentMethod,
    PaymentMethodSummary,
)
from sqlalchemy import func
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


class AccountService:
    def __init__(self, session_factory: SessionFactory = create_session) -> None:
        self._session_factory = session_factory

    def get_account_details(self, account_id: str, customer_id: str) -> Account | None:
        logger.info("Request to get_account_details with account_id: %s", account_id)
        _require_identifier(account_id, "AccountId")
        with self._session_factory() as session:
            account_product = _get_owned_product(
                session,
                account_id,
                customer_id,
                ACCOUNT_PRODUCT_TYPES,
            )
            customer = session.get(Customer, customer_id)
            if customer is None:
                raise PermissionError("Account does not belong to the authenticated customer")
            cards = list(
                session.exec(
                    select(Product)
                    .where(Product.customer_id == customer_id)
                    .where(Product.product_type.in_(CARD_PRODUCT_TYPES))
                    .order_by(Product.product_id)
                ).all()
            )
            return _to_account(project_runtime(session, account_product), customer, [project_runtime(session, card) for card in cards])

    def get_payment_method_details(
        self,
        payment_method_id: str,
        customer_id: str,
    ) -> PaymentMethod | None:
        logger.info(
            "Request to get_payment_method_details with payment_method_id: %s",
            payment_method_id,
        )
        _require_identifier(payment_method_id, "PaymentMethodId")
        with self._session_factory() as session:
            product = _get_owned_product(session, payment_method_id, customer_id)
            return _to_payment_method(project_runtime(session, product))

    def get_registered_beneficiary(
        self,
        account_id: str,
        customer_id: str,
    ) -> list[Beneficiary]:
        logger.info("Request to get_registered_beneficiary with account_id: %s", account_id)
        _require_identifier(account_id, "AccountId")
        with self._session_factory() as session:
            _get_owned_product(session, account_id, customer_id, ACCOUNT_PRODUCT_TYPES)
        raise RuntimeError("Registered beneficiaries are unavailable for persisted products")

    def list_accounts(self, customer_id: str) -> list[AccountSummary]:
        logger.info("Request to list_accounts for customer_id: %s", customer_id)
        with self._session_factory() as session:
            products = session.exec(
                select(Product)
                .where(Product.customer_id == customer_id)
                .where(Product.product_type.in_(ACCOUNT_PRODUCT_TYPES))
                .order_by(Product.product_id)
            ).all()
            return [_to_account_summary(project_runtime(session, product)) for product in products]


class UserService:
    def __init__(self, session_factory: SessionFactory = create_session) -> None:
        self._session_factory = session_factory

    def get_accounts_by_user_name(self, user_name: str, customer_id: str) -> list[Account]:
        _require_identifier(user_name, "UserName")
        with self._session_factory() as session:
            customer = session.exec(
                select(Customer)
                .where(Customer.customer_id == customer_id)
                .where(Customer.email == user_name.strip().lower())
            ).first()
            if customer is None:
                raise PermissionError("Account does not belong to the authenticated customer")

            products = list(
                session.exec(
                    select(Product)
                    .where(Product.customer_id == customer_id)
                    .where(Product.product_type.in_(ACCOUNT_PRODUCT_TYPES))
                    .order_by(Product.product_id)
                ).all()
            )
            return [_to_account(project_runtime(session, product), customer, []) for product in products]


class CardService:
    def __init__(self, session_factory: SessionFactory = create_session) -> None:
        self._session_factory = session_factory

    def get_credit_cards(self, account_id: str, customer_id: str) -> list[Card]:
        logger.info("Request to get_credit_cards with account_id: %s", account_id)
        _require_identifier(account_id, "AccountId")
        with self._session_factory() as session:
            _get_owned_product(session, account_id, customer_id, ACCOUNT_PRODUCT_TYPES)
            products = session.exec(
                select(Product)
                .where(Product.customer_id == customer_id)
                .where(Product.product_type.in_(CARD_PRODUCT_TYPES))
                .order_by(Product.product_id)
            ).all()
            return [_to_card(project_runtime(session, product)) for product in products]

    def get_card_details(self, card_id: str, customer_id: str) -> Card | None:
        logger.info("Request to get_card_details for card_id=%s", card_id)
        _require_identifier(card_id, "CardId")
        with self._session_factory() as session:
            product = _get_owned_product(session, card_id, customer_id, CARD_PRODUCT_TYPES)
            return _to_card(project_runtime(session, product))

    def list_cards(self, customer_id: str) -> list[CardSummary]:
        logger.info("Request to list_cards for customer_id: %s", customer_id)
        with self._session_factory() as session:
            products = session.exec(
                select(Product)
                .where(Product.customer_id == customer_id)
                .where(Product.product_type.in_(CARD_PRODUCT_TYPES))
                .order_by(Product.product_id)
            ).all()
            return [_to_card_summary(project_runtime(session, product)) for product in products]

    def discover_cards_by_suffix(self, suffix: str, customer_id: str) -> CardDiscoveryResult:
        if not re.fullmatch(r"[0-9]{4}", suffix):
            raise ValueError("Card suffix must be exactly four ASCII digits")
        _require_identifier(customer_id, "CustomerId")
        with self._session_factory() as session:
            products = session.exec(
                select(Product)
                .where(Product.customer_id == customer_id)
                .where(Product.product_type.in_(CARD_PRODUCT_TYPES))
                .where(func.rtrim(Product.product_number, " \t\n\r\v\f-").endswith(suffix))
                .order_by(Product.product_id)
                .limit(6)
            ).all()
            candidates = [
                CardDiscoveryCandidate(
                    masked_number=_masked_card_number(product.product_number),
                    type=product.product_type,
                    currency=product.currency,
                    status=project_runtime(session, product).product_status,
                    lookup_product_number=_verified_card_lookup_number(
                        session, product, customer_id
                    ),
                )
                for product in products[:5]
            ]
            if not products:
                return CardDiscoveryResult(status="NO_MATCH", candidates=[])
            if len(products) > 1:
                return CardDiscoveryResult(
                    status="TOO_MANY_MATCHES" if len(products) > 5 else "AMBIGUOUS",
                    candidates=candidates,
                    truncated=len(products) > 5,
                )
            return CardDiscoveryResult(
                status="MATCH" if candidates[0].lookup_product_number else "LOOKUP_UNAVAILABLE",
                candidates=candidates,
            )

    def recharge_card(self, card_id: str, amount: float, customer_id: str) -> Card:
        self._authorize_card(card_id, customer_id)
        if amount <= 0:
            raise ValueError("Amount must be greater than zero")
        raise RuntimeError("Card recharge is unavailable for persisted products")

    def pay_with_card(self, card_id: str, amount: float, customer_id: str) -> Card:
        self._authorize_card(card_id, customer_id)
        if amount <= 0:
            raise ValueError("Amount must be greater than zero")
        raise RuntimeError("Card payment is unavailable for persisted products")

    def _authorize_card(self, card_id: str, customer_id: str) -> None:
        _require_identifier(card_id, "CardId")
        with self._session_factory() as session:
            _get_owned_product(session, card_id, customer_id, CARD_PRODUCT_TYPES)


card_service_singleton = CardService()
account_service_singleton = AccountService()


def _require_identifier(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} is empty or null")


def _get_owned_product(
    session: Session,
    product_id: str,
    customer_id: str,
    product_types: tuple[str, ...] | None = None,
) -> Product:
    statement = (
        select(Product)
        .where(Product.product_number == product_id)
        .where(Product.customer_id == customer_id)
    )
    if product_types is not None:
        statement = statement.where(Product.product_type.in_(product_types))
    products = session.exec(statement.limit(2)).all()
    if len(products) != 1:
        raise PermissionError("Account does not belong to the authenticated customer")
    return products[0]


def _verified_card_lookup_number(
    session: Session, product: Product, customer_id: str
) -> str | None:
    number = product.product_number
    if not number or not re.fullmatch(r"[0-9]{12,19}", re.sub(r"[\s-]", "", number)):
        return None
    try:
        verified = _get_owned_product(session, number, customer_id)
    except PermissionError:
        return None
    return number if verified.product_id == product.product_id else None


def _to_account(product: Product, customer: Customer, cards: list[Product]) -> Account:
    full_name = " ".join(
        part for part in (customer.first_name, customer.last_name) if part
    )
    return Account(
        accountNumber=(
            product.product_number.strip()
            if product.product_number and product.product_number.strip()
            else None
        ),
        userName=customer.email,
        accountHolderFullName=full_name,
        currency=product.currency,
        activationDate=_date_value(product.opening_date),
        balance=_decimal_text(product.current_balance),
        paymentMethods=[_to_payment_method_summary(card) for card in cards] or None,
    )


def _masked_card_number(number: str | None) -> str | None:
    compact = re.sub(r"[\s-]", "", number or "")
    if re.fullmatch(r"[0-9]{4}\*+[0-9]{4}", compact):
        return f"{compact[:4]} **** **** {compact[-4:]}"
    if re.fullmatch(r"\*+[0-9]{4}", compact):
        return f"**** {compact[-4:]}"
    if not re.fullmatch(r"[0-9]{12,19}", compact):
        return None
    return f"{compact[:4]} **** **** {compact[-4:]}"


def _to_payment_method_summary(product: Product) -> PaymentMethodSummary:
    return PaymentMethodSummary(
        number=_masked_card_number(product.product_number),
        type=card_type(product.product_type),
        activationDate=_date_value(product.opening_date),
        expirationDate=_date_value(product.expiration_date),
    )


def _to_payment_method(product: Product) -> PaymentMethod:
    return PaymentMethod(
        type=card_type(product.product_type),
        cardNumber=_masked_card_number(product.product_number),
        activationDate=_date_value(product.opening_date),
        expirationDate=_date_value(product.expiration_date),
        availableBalance=_decimal_float(product.current_balance),
        status=product.product_status,
    )


def _to_account_summary(product: Product) -> AccountSummary:
    return AccountSummary(
        product_id=product.product_id,
        type=normalize_product_type(product.product_type),
        status=product.product_status,
        opened=_date_value(product.opening_date),
        number=product.product_number,
        currency=product.currency,
        balance=_decimal_text(product.current_balance),
    )


def _to_card_summary(product: Product) -> CardSummary:
    return CardSummary(
        product_id=product.product_id,
        type=normalize_product_type(product.product_type),
        status=product.product_status,
        opened=_date_value(product.opening_date),
        expires=_date_value(product.expiration_date),
        number=_masked_card_number(product.product_number),
        currency=product.currency,
        balance=_decimal_text(product.current_balance),
        credit_limit=_decimal_text(product.credit_limit),
    )


def _to_card(product: Product) -> Card:
    return Card(
        type=card_type(product.product_type),
        number=_masked_card_number(product.product_number),
        name=normalize_product_type(product.product_type),
        activationDate=_date_value(product.opening_date),
        expirationDate=_date_value(product.expiration_date),
        balance=_decimal_float(product.current_balance),
        limit=_decimal_float(product.credit_limit),
        status=product.product_status,
    )


def _date_value(value: object | None) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else None


def _decimal_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _decimal_text(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None
