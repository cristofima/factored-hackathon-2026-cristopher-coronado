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
from sqlalchemy import event, func
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlmodel import Session, create_engine, select

from banking_transaction.auth.operator_identity import OperatorPrincipal
from banking_transaction.services.operator import OperatorCaseService, OperatorClaimConflict

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
        claimed_at, updated_at, audit_id = case.claimed_at, case.updated_at, audit.event_id

    for principal in operators:
        with pytest.raises(OperatorClaimConflict):
            postgres_service.claim_case("case", principal)
    with postgres_factory() as session:
        case = session.get(SupportCase, "case")
        assert case is not None and case.assigned_operator_sub == winner
        assert case.claim_version == 1 and case.claimed_at == claimed_at
        assert case.updated_at == updated_at and case.status == "IN_REVIEW"
        assert case.resolution_outcome is None and case.resolved_at is None
        audits = session.exec(select(SupportCaseEvent).where(
            SupportCaseEvent.case_id == "case",
            SupportCaseEvent.event_type == "OPERATOR_CLAIMED",
        )).all()
        assert [audit.event_id for audit in audits] == [audit_id]


@pytest.mark.parametrize("failure_stage", ["after_flush_postexec", "before_commit"])
def test_postgres_failed_claim_rolls_back_owner_version_and_written_audit(
    postgres_factory: Callable[[], Session], failure_stage: str,
) -> None:
    with postgres_factory() as session:
        original = session.get(SupportCase, "case")
        assert original is not None
        original_updated_at = original.updated_at

    def fail_write(session: Session, *args: object) -> None:
        raise RuntimeError("Synthetic post-write failure")

    def failing_factory() -> Session:
        session = postgres_factory()
        event.listen(session, failure_stage, fail_write)
        return session

    with pytest.raises(RuntimeError, match="Synthetic post-write failure"):
        OperatorCaseService(failing_factory).claim_case("case", OperatorPrincipal("operator-one", 1))
    with postgres_factory() as session:
        case = session.get(SupportCase, "case")
        assert case is not None
        assert case.assigned_operator_sub is None and case.claimed_at is None
        assert case.claim_version == 0 and case.updated_at == original_updated_at
        assert case.status == "IN_REVIEW" and case.resolved_at is None
        assert case.resolution_outcome is None
        assert session.exec(select(SupportCaseEvent).where(
            SupportCaseEvent.case_id == "case",
            SupportCaseEvent.event_type == "OPERATOR_CLAIMED",
        )).all() == []
        consent = session.exec(select(SupportCaseEvent).where(
            SupportCaseEvent.case_id == "case",
            SupportCaseEvent.event_type == "APPROVAL_GRANTED",
        )).one()
        assert consent.actor == "customer"

    service = OperatorCaseService(postgres_factory)
    assert service.list_cases(OperatorPrincipal("operator-one", 1)).total == 1
    recovered = service.claim_case("case", OperatorPrincipal("operator-two", 2))
    assert recovered.assignedOperatorSub == "operator-two" and recovered.claimVersion == 1
    claims = [item for item in recovered.events if item.eventType == "OPERATOR_CLAIMED"]
    assert len(claims) == 1 and claims[0].actor == "operator"


def prepare_financial_case(factory: Callable[[], Session]) -> tuple[OperatorCaseService, int]:
    from adjudication import advance, capture_evidence

    with factory() as session:
        product = session.get(Product, "product")
        transaction = session.get(TransactionRecord, "transaction")
        assert product is not None and transaction is not None
        product.product_type = "Credit Card"
        product.product_status = "Active"
        product.current_balance = Decimal("100")
        transaction.transaction_status = "Approved"
        session.add_all([product, transaction])
        session.commit()
    service = OperatorCaseService(factory)
    principal = OperatorPrincipal("operator-one", 1)
    service.claim_case("case", principal)
    with factory() as session:
        case = session.get(SupportCase, "case")
        assert case is not None
        capture_evidence(session, case)
        case.status = "PENDING_EFFECTS"
        case.verdict = "valid"
        advance(case)
        session.add(case)
        session.commit()
        version = case.case_version
    return service, version


def test_postgres_concurrent_effect_retry_posts_once(
    postgres_factory: Callable[[], Session],
) -> None:
    from adjudication import AdjudicationConflict
    from banking_shared.models import RuntimePosting
    from banking_shared.runtime import effective_balance

    service, version = prepare_financial_case(postgres_factory)
    barrier = Barrier(2)

    def retry(_: int) -> str:
        barrier.wait(timeout=10)
        try:
            return service.retry_effects("case", OperatorPrincipal("operator-one", 1), version).status
        except AdjudicationConflict as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(retry, range(2)))
    assert sorted(results) == ["CASE_VERSION_CONFLICT", "RESOLVED_VALID"]
    with postgres_factory() as session:
        assert len(session.exec(select(RuntimePosting)).all()) == 1
        assert len(session.exec(select(TransactionRecord).where(
            TransactionRecord.source_kind == "runtime",
        )).all()) == 1
        product = session.get(Product, "product")
        assert product is not None and effective_balance(session, product) == Decimal("90")
        effects = session.exec(select(SupportCaseEvent).where(
            SupportCaseEvent.event_type == "FINANCIAL_EFFECT_EXECUTED",
        )).all()
        assert len(effects) == 1


def test_postgres_lifetime_entitlement_is_serialized_across_historical_cases(
    postgres_factory: Callable[[], Session],
) -> None:
    from adjudication import execute_effects, source_snapshot
    from banking_shared.models import RuntimePosting

    prepare_financial_case(postgres_factory)
    with postgres_factory() as session:
        original = session.get(SupportCase, "case")
        assert original is not None
        # Legacy historical cases are terminal; only one execution may consume entitlement.
        original.status = "RESOLVED"
        second = SupportCase(
            case_id="second", customer_id="customer", product_id="product",
            transaction_id="transaction", reason="Historical second case", status="RESOLVED",
            verdict="valid", assigned_operator_sub="operator-two",
            claimed_at=datetime.now(timezone.utc),
        )
        second.evidence_snapshot = source_snapshot(session, original)
        second.evidence_version = 1
        session.add_all([original, second])
        session.commit()
    barrier = Barrier(2)

    def execute(case_id: str) -> str:
        with postgres_factory() as session:
            case = session.get(SupportCase, case_id)
            assert case is not None
            case.status = "PENDING_EFFECTS"
            barrier.wait(timeout=10)
            assert case.assigned_operator_sub is not None
            with session.no_autoflush:
                execute_effects(session, case, OperatorPrincipal(case.assigned_operator_sub, 1), None)
            session.add(case)
            session.commit()
            return case.effect_code or case.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(execute, ["case", "second"]))
    assert sorted(results) == ["CREDIT_ALREADY_APPLIED", "RESOLVED_VALID"]
    with postgres_factory() as session:
        assert len(session.exec(select(RuntimePosting)).all()) == 1


def test_postgres_concurrent_active_intake_is_unique(
    postgres_factory: Callable[[], Session],
) -> None:
    from sqlalchemy.exc import IntegrityError

    with postgres_factory() as session:
        case = session.get(SupportCase, "case")
        assert case is not None
        case.status = "RESOLVED_INVALID"
        session.add(case)
        session.commit()
    barrier = Barrier(2)

    def intake(case_id: str) -> str:
        with postgres_factory() as session:
            session.add(SupportCase(
                case_id=case_id, customer_id="customer", product_id="product",
                transaction_id="transaction", reason="Concurrent intake", status="IN_REVIEW",
            ))
            barrier.wait(timeout=10)
            try:
                session.commit()
                return "created"
            except IntegrityError:
                session.rollback()
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(intake, ["one", "two"]))
    assert sorted(results) == ["conflict", "created"]
