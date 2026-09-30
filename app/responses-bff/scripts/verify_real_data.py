"""Read-only PostgreSQL parity checks; output never includes identities or amounts."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import logging
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time as day_time, timezone
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

from banking_shared.database import get_database_url
from banking_shared.models import Customer, Product, TransactionRecord, User
from sqlalchemy import func
from sqlmodel import Session, create_engine, select

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "app/responses-bff"))

from bff.user_repository import SqlModelUserRepository

START = date(2026, 6, 1)
END = date(2026, 6, 17)
ACCOUNT_TYPES = ("Cuenta Ahorro", "Cuenta Corriente")
CARD_TYPES = ("Tarjeta Cr\u00e9dito", "Tarjeta D\u00e9bito")
EMAILS = ("mariana.flores@gmail.com", "raul.contreras518@hotmail.com")


@dataclass
class Evidence:
    checks: dict[str, bool]
    counts: dict[str, int]

    def equal(self, name: str, actual: object, expected: object) -> None:
        self.checks[name] = self.checks.get(name, True) and actual == expected

    def denied(self, name: str, action: Callable[[], object]) -> None:
        try:
            action()
        except PermissionError:
            self.equal(name, True, True)
        else:
            self.equal(name, False, True)


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Verification module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_service(kind: str) -> tuple[ModuleType, ModuleType]:
    directory = ROOT / "app/business-api" / kind
    previous = sys.modules.get("models")
    sys.modules["models"] = load_module(f"verify_{kind}_models", directory / "models.py")
    try:
        service = load_module(f"verify_{kind}_services", directory / "services.py")
    finally:
        if previous is None:
            sys.modules.pop("models", None)
        else:
            sys.modules["models"] = previous
    return service, load_module(f"verify_{kind}_identity", directory / "internal_identity.py")


def verified_customer(user: User, secret: str, identity: ModuleType) -> str:
    payload = json.dumps({"sub": user.id, "customer_id": user.customer_id,
                          "exp": int(time.time()) + 60}, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return identity.get_customer_id({"authorization": f"Bearer v1.{encoded}.{signature}"})


def iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def card_type(product: Product) -> str:
    return {CARD_TYPES[0]: "credit", CARD_TYPES[1]: "debit"}.get(
        product.product_type, product.product_type
    )


def fields_equal(actual: Any, expected: dict[str, object]) -> bool:
    return all(getattr(actual, field) == value for field, value in expected.items())


def account_expected(product: Product, customer: Customer) -> dict[str, object]:
    return {"id": product.product_id, "userName": customer.email,
            "accountHolderFullName": " ".join(filter(None, (customer.first_name,
                                                           customer.last_name))),
            "currency": product.currency, "activationDate": iso(product.opening_date),
            "balance": format(product.current_balance, "f")
            if product.current_balance is not None else None}


def card_expected(product: Product) -> dict[str, object]:
    return {"id": product.product_id, "type": card_type(product), "name": product.product_type,
            "activationDate": iso(product.opening_date),
            "expirationDate": iso(product.expiration_date), "status": product.product_status,
            "balance": float(product.current_balance)
            if product.current_balance is not None else None,
            "limit": float(product.credit_limit) if product.credit_limit is not None else None,
            "circuit": None, "number": None, "cvv": None, "rechargedAmount": None}


def transaction_expected(record: TransactionRecord, product: Product) -> dict[str, object]:
    return {"id": record.transaction_id, "type": record.transaction_type,
            "recipientName": record.merchant_name, "accountId": record.product_id,
            "paymentType": record.channel, "amount": float(record.amount),
            "timestamp": iso(record.transaction_date), "category": record.transaction_category,
            "status": record.transaction_status,
            "cardId": record.product_id if product.product_type in CARD_TYPES else None,
            "description": None, "flowType": None, "recipientBankReference": None}


def compare_transactions(evidence: Evidence, name: str, actual: list[Any],
                         expected: list[TransactionRecord], product: Product) -> None:
    evidence.equal(name, len(actual) == len(expected) and all(
        fields_equal(item, transaction_expected(record, product))
        for item, record in zip(actual, expected)
    ), True)
    evidence.equal("transaction_amounts_exact", all(
        Decimal(str(item.amount)) == record.amount
        for item, record in zip(actual, expected)
    ), True)


def verify_pages(evidence: Evidence, repo: SqlModelUserRepository, user: User,
                 product: Product, expected: list[TransactionRecord]) -> None:
    collected: list[TransactionRecord] = []
    for offset in range(0, len(expected) + 7, 7):
        result = repo.list_transactions(user.id, user.customer_id, product.product_id,
                                        START, END, 7, offset)
        if result is None:
            evidence.equal("bff_pagination", False, True)
            return
        items, total = result
        evidence.equal("bff_total", total, len(expected))
        evidence.equal("bff_page_fields", [item.model_dump() for item in items],
                       [item.model_dump() for item in expected[offset:offset + 7]])
        collected.extend(items)
        evidence.counts["bff_pages"] += 1
    evidence.equal("bff_pagination", [item.model_dump() for item in collected],
                   [item.model_dump() for item in expected])
    evidence.equal("bff_empty_window", repo.list_transactions(
        user.id, user.customer_id, product.product_id, date(1900, 1, 1),
        date(1900, 1, 1), 7, 0), ([], 0))


def verify_filters(evidence: Evidence, service: Any, product: Product, customer_id: str,
                   rows: list[TransactionRecord]) -> None:
    compare_transactions(evidence, "transaction_latest", service.get_transactions(
        product.product_id, customer_id), rows[:5], product)
    compare_transactions(evidence, "transaction_unfiltered", service.get_transactions_by_type(
        product.product_id, customer_id), rows, product)
    for field, argument in (("transaction_type", "transaction_type"), ("channel", "payment_type")):
        for value in {getattr(row, field) for row in rows} - {None, ""}:
            compare_transactions(evidence, f"transaction_{argument}",
                                 service.get_transactions_by_type(product.product_id, customer_id,
                                                                  **{argument: value}),
                                 [row for row in rows if getattr(row, field) == value], product)
            evidence.counts["filter_queries"] += 1
    compare_transactions(evidence, "transaction_empty_filter", service.get_transactions_by_type(
        product.product_id, customer_id, transaction_type=str(uuid4())), [], product)
    merchant = next((row.merchant_name for row in rows if row.merchant_name), None)
    fragment = re.search(r"[A-Za-z0-9]+", merchant or "")
    if fragment:
        name = fragment.group()
        compare_transactions(evidence, "transaction_recipient",
                             service.get_transactions_by_recipient_name(
                                 product.product_id, name, customer_id),
                             [row for row in rows if name.lower() in
                              (row.merchant_name or "").lower()], product)
    compare_transactions(evidence, "transaction_empty_recipient",
                         service.get_transactions_by_recipient_name(
                             product.product_id, str(uuid4()), customer_id), [], product)


def verify_user(session: Session, factory: Callable[[], Session], user: User, foreign: User,
                account_module: ModuleType, transaction_module: ModuleType,
                customer_id: str) -> dict[str, object]:
    evidence = Evidence({}, {"bff_pages": 0, "filter_queries": 0})
    repo = SqlModelUserRepository(factory)
    accounts = account_module.AccountService(factory)
    cards = account_module.CardService(factory)
    users = account_module.UserService(factory)
    transactions = transaction_module.TransactionService(factory)
    customer = session.exec(select(Customer).where(Customer.customer_id == user.customer_id)).one()
    products = list(session.exec(select(Product).where(
        Product.customer_id == user.customer_id).order_by(Product.product_id)).all())
    owned_accounts = [product for product in products if product.product_type in ACCOUNT_TYPES]
    owned_cards = [product for product in products if product.product_type in CARD_TYPES]
    all_rows = list(session.exec(select(TransactionRecord).where(
        TransactionRecord.customer_id == user.customer_id).order_by(
        TransactionRecord.transaction_date.desc(), TransactionRecord.transaction_id.desc())).all())
    window_rows = [row for row in all_rows if START <= row.transaction_date.date() <= END]
    evidence.equal("verified_customer", customer_id, user.customer_id)
    evidence.equal("bff_identity_fields", repo.find_by_email(user.email).model_dump(),
                   user.model_dump())
    evidence.equal("bff_account_fields_exact", [item.model_dump() for item in repo.list_accounts(
        user.id, customer_id)], [item.model_dump() for item in owned_accounts])
    name = " ".join(part.strip() for part in (customer.first_name, customer.last_name)
                    if part and part.strip()) or None
    evidence.equal("bff_name", repo.find_customer_name(user.id, customer_id), name)
    listed = users.get_accounts_by_user_name(user.email, customer_id)
    evidence.equal("account_list", len(listed) == len(owned_accounts) and all(
        fields_equal(item, account_expected(product, customer)) and item.paymentMethods is None
        for item, product in zip(listed, owned_accounts)), True)
    evidence.equal("transaction_customer_product_scope", all(
        row.product_id in {product.product_id for product in products} for row in all_rows), True)
    for product in products:
        product_rows = list(session.exec(select(TransactionRecord).where(
            TransactionRecord.product_id == product.product_id).order_by(
            TransactionRecord.transaction_date.desc(), TransactionRecord.transaction_id.desc())).all())
        evidence.equal("transaction_product_customer_scope", all(
            row.customer_id == customer_id for row in product_rows), True)
        rows = [row for row in all_rows if row.product_id == product.product_id]
        verify_filters(evidence, transactions, product, customer_id, rows)
        if product.product_type in ACCOUNT_TYPES:
            verify_pages(evidence, repo, user, product,
                         [row for row in window_rows if row.product_id == product.product_id])
            detail = accounts.get_account_details(product.product_id, customer_id)
            evidence.equal("account_details", fields_equal(detail, account_expected(
                product, customer)), True)
            summaries = [{"id": card.product_id, "type": card_type(card), "name": None,
                          "activationDate": iso(card.opening_date),
                          "expirationDate": iso(card.expiration_date)} for card in owned_cards]
            evidence.equal("account_card_summaries", [item.model_dump() for item in
                           (detail.paymentMethods or [])], summaries)
            returned = cards.get_credit_cards(product.product_id, customer_id)
            evidence.equal("cards_list", len(returned) == len(owned_cards) and all(
                fields_equal(item, card_expected(card))
                for item, card in zip(returned, owned_cards)), True)
            for card in owned_cards:
                compare_transactions(evidence, "transaction_card_filter",
                    transactions.get_transactions_by_type(product.product_id, customer_id,
                                                          card_id=card.product_id),
                    [row for row in all_rows if row.product_id == card.product_id], card)
        if product.product_type in CARD_TYPES:
            card = cards.get_card_details(product.product_id, customer_id)
            evidence.equal("card_details", fields_equal(card, card_expected(product)), True)
            evidence.equal("card_balances_exact", card.balance is None
                           if product.current_balance is None else
                           Decimal(str(card.balance)) == product.current_balance, True)
    foreign_product = session.exec(select(Product).where(
        Product.customer_id == foreign.customer_id, Product.product_type.in_(ACCOUNT_TYPES))).first()
    missing = str(uuid4())
    evidence.equal("missing_product_verified", session.get(Product, missing), None)
    for label, identifier in (("missing", missing), ("foreign", foreign_product.product_id)):
        evidence.equal(f"bff_{label}", repo.list_transactions(
            user.id, customer_id, identifier, START, END, 7, 0), None)
        for method in (accounts.get_account_details, cards.get_credit_cards,
                       transactions.get_transactions, transactions.get_transactions_by_type):
            evidence.denied(f"services_{label}", lambda method=method: method(
                identifier, customer_id))
    evidence.equal("bff_mismatched_accounts", repo.list_accounts(user.id, foreign.customer_id), [])
    evidence.equal("bff_mismatched_name", repo.find_customer_name(user.id, foreign.customer_id), None)
    evidence.equal("bff_mismatched_transactions", repo.list_transactions(
        user.id, foreign.customer_id, foreign_product.product_id, START, END, 7, 0), None)
    evidence.denied("account_mismatched_email", lambda: users.get_accounts_by_user_name(
        foreign.email, customer_id))
    evidence.counts.update(accounts=len(owned_accounts), cards=len(owned_cards),
                           products=len(products), window_transactions=len(window_rows),
                           account_window_transactions=sum(row.product_id in {
                               product.product_id for product in owned_accounts}
                               for row in window_rows), all_transactions=len(all_rows))
    return {"counts": evidence.counts, "equalities": evidence.checks,
            "currencies": sorted({row.currency for row in window_rows}),
            "types": sorted({row.transaction_type for row in window_rows if row.transaction_type}),
            "statuses": sorted({row.transaction_status for row in window_rows
                                if row.transaction_status}),
            "date_bounds": [iso(min((row.transaction_date.date() for row in window_rows),
                                     default=None)),
                            iso(max((row.transaction_date.date() for row in window_rows),
                                     default=None))]}


def main() -> int:
    logging.disable(logging.CRITICAL)
    engine = create_engine(get_database_url(), echo=False, hide_parameters=True,
                           connect_args={"options": "-c default_transaction_read_only=on"})
    try:
        if engine.dialect.name != "postgresql":
            raise RuntimeError("PostgreSQL required")
        account, account_identity = load_service("account")
        transaction, transaction_identity = load_service("transaction")
        secret = os.environ.get("INTERNAL_IDENTITY_SECRET", "")
        if not secret:
            raise RuntimeError("Internal identity configuration required")
        with engine.connect().execution_options(isolation_level="REPEATABLE READ",
                                                postgresql_readonly=True) as connection:
            with connection.begin():
                def factory() -> Session:
                    return Session(connection, join_transaction_mode="rollback_only")

                with factory() as session:
                    readonly = session.exec(select(func.current_setting("transaction_read_only")))
                    if readonly.one() != "on":
                        raise RuntimeError("Read-only transaction required")
                    identities = [session.exec(select(User).where(User.email == email)).one()
                                  for email in EMAILS]
                    report: dict[str, Any] = {"read_only": True, "window": [iso(START), iso(END)]}
                    for index, user in enumerate(identities):
                        customer_id = verified_customer(user, secret, account_identity)
                        if verified_customer(user, secret, transaction_identity) != customer_id:
                            raise RuntimeError("Identity verification mismatch")
                        report[f"user-{index + 1}"] = verify_user(
                            session, factory, user, identities[1 - index], account, transaction,
                            customer_id)
                    report["passed"] = all(all(report[alias]["equalities"].values())
                                           for alias in ("user-1", "user-2"))
                    print(json.dumps(report, indent=2, ensure_ascii=True))
                    connection.rollback()
                    return 0 if report["passed"] else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as error:
        print(json.dumps({"passed": False, "error_class": type(error).__name__}))
        exit_code = 2
    sys.exit(exit_code)