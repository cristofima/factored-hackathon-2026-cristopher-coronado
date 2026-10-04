"""Opt-in PostgreSQL race test in a disposable, uniquely named schema."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import os
from threading import Barrier
from uuid import uuid4

import pytest
from banking_shared.models import (
    Customer, Product, SQLModel, SupportCase, SupportCaseEvent, TransactionRecord,
)
from banking_shared.identity_models import User, Operator
from sqlalchemy import func
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlmodel import Session, create_engine, select

from operator_identity import OperatorPrincipal
from operator_service import OperatorCaseService, OperatorClaimConflict

pytestmark = pytest.mark.skipif(
    os.getenv("OPERATOR_TEST_ALLOW_WRITES") != "1"
    or not os.getenv("OPERATOR_TEST_DATABASE_URL"),
    reason="Explicit disposable PostgreSQL target and write authorization required",
)


@pytest.fixture
def postgres_factory() -> Iterator[Callable[[], Session]]:
    engine = create_engine(os.environ["OPERATOR_TEST_DATABASE_URL"])
    assert engine.dialect.name == "postgresql", "A PostgreSQL target is required"
    schema = "operator_claim_test_" + uuid4().hex
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        isolated = engine.execution_options(schema_translate_map={None: schema})
        SQLModel.metadata.create_all(isolated)
        now = datetime.now(timezone.utc)
        with Session(isolated) as session:
            for subject in ("operator-one", "operator-two"):
                session.add(User(
                    id=subject, email=f"{subject}@synthetic.invalid",
                    password_hash="unused-test-hash", locale="en", status="active",
                ))
            session.flush()
            session.add_all([Operator(user_id="operator-one"), Operator(user_id="operator-two")])
            session.flush()
            session.add(Customer(customer_id="customer", email="customer@synthetic.invalid"))
            session.flush()
            session.add(Product(product_id="product", customer_id="customer",
                                product_type="Checking", currency="USD"))
            session.flush()
            session.add(TransactionRecord(
                transaction_id="transaction", customer_id="customer", product_id="product",
                transaction_date=now, process_date=now.date(), amount=Decimal("10"), currency="USD",
            ))
            session.flush()
            session.add(SupportCase(
                case_id="case", customer_id="customer", product_id="product",
                transaction_id="transaction", reason="Synthetic dispute", status="IN_REVIEW",
            ))
            session.flush()
            session.add(SupportCaseEvent(case_id="case", actor="customer",
                                         event_type="APPROVAL_GRANTED"))
            session.commit()
        yield lambda: Session(isolated)
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        engine.dispose()


def test_postgres_concurrent_claim_has_one_winner_and_one_audit(
    postgres_factory: Callable[[], Session],
) -> None:
    postgres_service = OperatorCaseService(postgres_factory)
    barrier = Barrier(2)
    operators = [OperatorPrincipal("operator-one", 1), OperatorPrincipal("operator-two", 2)]

    def claim(principal: OperatorPrincipal) -> tuple[str, str]:
        barrier.wait(timeout=10)
        try:
            result = postgres_service.claim_case("case", principal)
            assert result.claimVersion == 1 and result.status == "IN_REVIEW"
            return "claimed", principal.sub
        except OperatorClaimConflict:
            return "conflict", principal.sub

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, operators))
    assert sorted(status for status, _ in results) == ["claimed", "conflict"]
    winner = next(subject for status, subject in results if status == "claimed")
    with postgres_factory() as session:
        case = session.get(SupportCase, "case")
        assert case is not None and case.assigned_operator_sub == winner
        assert case.claimed_at is not None and case.claim_version == 1
        assert case.resolution_outcome is None and case.resolved_at is None
        count = session.exec(select(func.count()).select_from(SupportCaseEvent).where(
            SupportCaseEvent.event_type == "OPERATOR_CLAIMED",
        )).one()
        assert count == 1
        audit = session.exec(select(SupportCaseEvent).where(
            SupportCaseEvent.event_type == "OPERATOR_CLAIMED",
        )).one()
        assert audit.operator_sub == winner and audit.claim_version == 1
        assert audit.operator_identity_version == next(
            principal.identity_version for principal in operators if principal.sub == winner
        )
