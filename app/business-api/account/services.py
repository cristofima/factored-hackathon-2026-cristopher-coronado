from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal

from banking_shared.database import create_session
from banking_shared.models import Customer, Product
from models import Account, Beneficiary, Card, PaymentMethod, PaymentMethodSummary
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

ACCOUNT_PRODUCT_TYPES = ("Cuenta Ahorro", "Cuenta Corriente")
CARD_PRODUCT_TYPES = ("Tarjeta Cr\u00e9dito", "Tarjeta D\u00e9bito")
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
            return _to_account(account_product, customer, cards)

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
            return _to_payment_method(product)

    def get_registered_beneficiary(
        self,
        account_id: str,
        customer_id: str,
    ) -> list[Beneficiary]:
        logger.info("Request to get_registered_beneficiary with account_id: %s", account_id)
        _require_identifier(account_id, "AccountId")
        with self._session_factory() as session:
            _get_owned_product(session, account_id, customer_id, ACCOUNT_PRODUCT_TYPES)
        return []


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
            return [_to_account(product, customer, []) for product in products]


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
            return [_to_card(product) for product in products]

    def get_card_details(self, card_id: str, customer_id: str) -> Card | None:
        logger.info("Request to get_card_details for card_id=%s", card_id)
        _require_identifier(card_id, "CardId")
        with self._session_factory() as session:
            product = _get_owned_product(session, card_id, customer_id, CARD_PRODUCT_TYPES)
            return _to_card(product)

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
        .where(Product.product_id == product_id)
        .where(Product.customer_id == customer_id)
    )
    if product_types is not None:
        statement = statement.where(Product.product_type.in_(product_types))
    product = session.exec(statement).first()
    if product is None:
        raise PermissionError("Account does not belong to the authenticated customer")
    return product


def _to_account(product: Product, customer: Customer, cards: list[Product]) -> Account:
    full_name = " ".join(
        part for part in (customer.first_name, customer.last_name) if part
    )
    return Account(
        id=product.product_id,
        userName=customer.email,
        accountHolderFullName=full_name,
        currency=product.currency,
        activationDate=_date_value(product.opening_date),
        balance=_decimal_text(product.current_balance),
        paymentMethods=[_to_payment_method_summary(card) for card in cards] or None,
    )


def _to_payment_method_summary(product: Product) -> PaymentMethodSummary:
    return PaymentMethodSummary(
        id=product.product_id,
        type=_card_type(product.product_type),
        activationDate=_date_value(product.opening_date),
        expirationDate=_date_value(product.expiration_date),
    )


def _to_payment_method(product: Product) -> PaymentMethod:
    return PaymentMethod(
        id=product.product_id,
        type=_card_type(product.product_type),
        activationDate=_date_value(product.opening_date),
        expirationDate=_date_value(product.expiration_date),
        availableBalance=_decimal_float(product.current_balance),
        status=product.product_status,
    )


def _to_card(product: Product) -> Card:
    return Card(
        id=product.product_id,
        type=_card_type(product.product_type),
        name=product.product_type,
        activationDate=_date_value(product.opening_date),
        expirationDate=_date_value(product.expiration_date),
        balance=_decimal_float(product.current_balance),
        limit=_decimal_float(product.credit_limit),
        status=product.product_status,
    )


def _card_type(product_type: str) -> str:
    if product_type == "Tarjeta Cr\u00e9dito":
        return "credit"
    if product_type == "Tarjeta D\u00e9bito":
        return "debit"
    return product_type


def _date_value(value: object | None) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else None


def _decimal_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _decimal_text(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None
