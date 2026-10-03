"""Ownership and state-machine checks for the transaction-dispute support-case workflow."""

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from banking_shared.models import (
    Customer,
    Product,
    ServiceAgent,
    SQLModel,
    SupportCase,
    TransactionRecord,
)
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from dispute_service import SupportCaseService

NOW = datetime.now(timezone.utc)


@pytest.fixture
def session_factory() -> Callable[[], Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Customer(customer_id="customer-owned", email="owner@example.com"),
                Customer(customer_id="customer-foreign", email="foreign@example.com"),
                Product(
                    product_id="card-owned",
                    product_number="4111111111111111",
                    customer_id="customer-owned",
                    product_type="Credit Card",
                    currency="USD",
                    product_status="Active",
                ),
                Product(
                    product_id="card-blocked",
                    product_number="4222222222222222",
                    customer_id="customer-owned",
                    product_type="Credit Card",
                    currency="USD",
                    product_status="Blocked",
                ),
                ServiceAgent(
                    agent_id="agent-1",
                    agent_status="Active",
                    specialty="Fraudes",
                ),
            ]
        )
        session.add_all(
            [
                TransactionRecord(
                    transaction_id="tx-low-risk",
                    transaction_date=NOW - timedelta(days=5),
                    process_date=date(2026, 6, 1),
                    product_id="card-owned",
                    customer_id="customer-owned",
                    amount=Decimal("120.0000"),
                    currency="USD",
                    transaction_status="Approved",
                    fraud_score=Decimal("10.0000"),
                ),
                TransactionRecord(
                    transaction_id="tx-high-risk",
                    transaction_date=NOW - timedelta(days=5),
                    process_date=date(2026, 6, 1),
                    product_id="card-owned",
                    customer_id="customer-owned",
                    amount=Decimal("330.0000"),
                    currency="USD",
                    transaction_status="Approved",
                    fraud_score=Decimal("87.0000"),
                ),
                TransactionRecord(
                    transaction_id="tx-no-score",
                    transaction_date=NOW - timedelta(days=5),
                    process_date=date(2026, 6, 1),
                    product_id="card-owned",
                    customer_id="customer-owned",
                    amount=Decimal("50.0000"),
                    currency="USD",
                    transaction_status="Approved",
                    fraud_score=None,
                ),
                TransactionRecord(
                    transaction_id="tx-declined",
                    transaction_date=NOW - timedelta(days=5),
                    process_date=date(2026, 6, 1),
                    product_id="card-owned",
                    customer_id="customer-owned",
                    amount=Decimal("75.0000"),
                    currency="USD",
                    transaction_status="Declined",
                    fraud_score=Decimal("5.0000"),
                ),
                TransactionRecord(
                    transaction_id="tx-too-old",
                    transaction_date=NOW - timedelta(days=366),
                    process_date=date(2025, 1, 1),
                    product_id="card-owned",
                    customer_id="customer-owned",
                    amount=Decimal("60.0000"),
                    currency="USD",
                    transaction_status="Approved",
                    fraud_score=Decimal("10.0000"),
                ),
                TransactionRecord(
                    transaction_id="tx-blocked-card",
                    transaction_date=NOW - timedelta(days=5),
                    process_date=date(2026, 6, 1),
                    product_id="card-blocked",
                    customer_id="customer-owned",
                    amount=Decimal("20.0000"),
                    currency="USD",
                    transaction_status="Approved",
                    fraud_score=Decimal("10.0000"),
                ),
                TransactionRecord(
                    transaction_id="tx-foreign",
                    transaction_date=NOW - timedelta(days=5),
                    process_date=date(2026, 6, 1),
                    product_id="card-owned",
                    customer_id="customer-foreign",
                    amount=Decimal("20.0000"),
                    currency="USD",
                    transaction_status="Approved",
                    fraud_score=Decimal("10.0000"),
                ),
            ]
        )
        session.commit()
    return lambda: Session(engine)


def test_low_fraud_score_case_is_fast_tracked_and_resolved(
    session_factory: Callable[[], Session],
) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-low-risk", "customer-owned", "No reconozco este cargo")
    assert opened.status == "WAITING_USER_APPROVAL"
    assert opened.productNumber == "**** 1111"

    resolved = service.respond_to_approval(opened.caseId, "customer-owned", approved=True)

    assert resolved.status == "RESOLVED"
    assert resolved.triageOutcome == "fast_track"
    assert resolved.resolutionOutcome == "fast_tracked_provisional_credit"


def test_high_fraud_score_case_is_escalated_to_a_fraud_agent(
    session_factory: Callable[[], Session],
) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-high-risk", "customer-owned", "Cargo sospechoso")

    escalated = service.respond_to_approval(opened.caseId, "customer-owned", approved=True)

    assert escalated.status == "IN_REVIEW"
    assert escalated.triageOutcome == "escalated"

    with session_factory() as session:
        case = session.get(SupportCase, escalated.caseId)
        assert case.assigned_agent_id == "agent-1"


def test_missing_fraud_score_escalates_as_insufficient_signal(
    session_factory: Callable[[], Session],
) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-no-score", "customer-owned", "No fue mi compra")

    escalated = service.respond_to_approval(opened.caseId, "customer-owned", approved=True)

    assert escalated.status == "IN_REVIEW"
    assert escalated.triageOutcome == "insufficient_signal"


def test_declining_approval_withdraws_the_case(session_factory: Callable[[], Session]) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-low-risk", "customer-owned", "Reclamo")

    declined = service.respond_to_approval(opened.caseId, "customer-owned", approved=False)

    assert declined.status == "RESOLVED"
    assert declined.resolutionOutcome == "withdrawn_by_customer"


def test_escalated_case_can_be_manually_resolved(session_factory: Callable[[], Session]) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-high-risk", "customer-owned", "Cargo sospechoso")
    service.respond_to_approval(opened.caseId, "customer-owned", approved=True)

    resolved = service.resolve_case(
        opened.caseId, "customer-owned", "fraud_confirmed_refund_issued", "Reviewed by agent-1"
    )

    assert resolved.status == "RESOLVED"
    assert resolved.resolutionOutcome == "fraud_confirmed_refund_issued"


def test_declined_transactions_cannot_be_disputed(session_factory: Callable[[], Session]) -> None:
    with pytest.raises(ValueError, match="Approved"):
        SupportCaseService(session_factory).open_transaction_dispute(
            "tx-declined", "customer-owned", "No reconozco"
        )


def test_transactions_within_one_year_can_be_disputed(
    session_factory: Callable[[], Session],
) -> None:
    with session_factory() as session:
        transaction = session.get(TransactionRecord, "tx-low-risk")
        assert transaction is not None
        transaction.transaction_date = NOW - timedelta(days=364)
        session.add(transaction)
        session.commit()

    opened = SupportCaseService(session_factory).open_transaction_dispute(
        "tx-low-risk", "customer-owned", "Unrecognized charge"
    )

    assert opened.status == "WAITING_USER_APPROVAL"


def test_transactions_outside_the_dispute_window_are_rejected(
    session_factory: Callable[[], Session],
) -> None:
    with pytest.raises(ValueError, match="dispute window"):
        SupportCaseService(session_factory).open_transaction_dispute(
            "tx-too-old", "customer-owned", "No reconozco"
        )


def test_blocked_card_cannot_open_a_new_dispute(session_factory: Callable[[], Session]) -> None:
    with pytest.raises(ValueError, match="Active"):
        SupportCaseService(session_factory).open_transaction_dispute(
            "tx-blocked-card", "customer-owned", "No reconozco"
        )


def test_duplicate_dispute_on_same_transaction_is_rejected(
    session_factory: Callable[[], Session],
) -> None:
    service = SupportCaseService(session_factory)
    service.open_transaction_dispute("tx-low-risk", "customer-owned", "Primer reclamo")

    with pytest.raises(ValueError, match="already has an active dispute"):
        service.open_transaction_dispute("tx-low-risk", "customer-owned", "Segundo reclamo")


def test_foreign_transaction_cannot_be_disputed(session_factory: Callable[[], Session]) -> None:
    with pytest.raises(PermissionError, match="authenticated customer"):
        SupportCaseService(session_factory).open_transaction_dispute(
            "tx-foreign", "customer-owned", "No reconozco"
        )


def test_foreign_customer_cannot_read_or_approve_another_customers_case(
    session_factory: Callable[[], Session],
) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-low-risk", "customer-owned", "Reclamo")

    with pytest.raises(PermissionError, match="authenticated customer"):
        service.get_case(opened.caseId, "customer-foreign")

    with pytest.raises(PermissionError, match="authenticated customer"):
        service.respond_to_approval(opened.caseId, "customer-foreign", approved=True)


def test_list_and_timeline_are_scoped_to_the_owning_customer(
    session_factory: Callable[[], Session],
) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-low-risk", "customer-owned", "Reclamo")

    cases = service.list_cases("customer-owned")
    timeline = service.get_case_timeline(opened.caseId, "customer-owned")

    assert [case.caseId for case in cases] == [opened.caseId]
    assert [event.eventType for event in timeline] == ["CASE_OPENED", "APPROVAL_REQUESTED"]
    assert service.list_cases("customer-foreign") == []


def test_fast_tracked_case_gets_a_recommendation(session_factory: Callable[[], Session]) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-low-risk", "customer-owned", "Reclamo")

    resolved = service.respond_to_approval(opened.caseId, "customer-owned", approved=True)

    assert resolved.recommendationType == "transaction_alerts"
    assert resolved.recommendationRationale
    assert resolved.recommendationOptedOut is False


def test_withdrawn_case_gets_no_recommendation(session_factory: Callable[[], Session]) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-low-risk", "customer-owned", "Reclamo")

    declined = service.respond_to_approval(opened.caseId, "customer-owned", approved=False)

    assert declined.recommendationType is None


def test_customer_can_dismiss_the_recommendation(session_factory: Callable[[], Session]) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-low-risk", "customer-owned", "Reclamo")
    resolved = service.respond_to_approval(opened.caseId, "customer-owned", approved=True)

    dismissed = service.dismiss_recommendation(resolved.caseId, "customer-owned")

    assert dismissed.recommendationOptedOut is True


def test_dismissing_a_recommendation_requires_one_to_exist(
    session_factory: Callable[[], Session],
) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-low-risk", "customer-owned", "Reclamo")
    service.respond_to_approval(opened.caseId, "customer-owned", approved=False)

    with pytest.raises(ValueError, match="no recommendation"):
        service.dismiss_recommendation(opened.caseId, "customer-owned")


def test_foreign_customer_cannot_dismiss_another_customers_recommendation(
    session_factory: Callable[[], Session],
) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-low-risk", "customer-owned", "Reclamo")
    resolved = service.respond_to_approval(opened.caseId, "customer-owned", approved=True)

    with pytest.raises(PermissionError, match="authenticated customer"):
        service.dismiss_recommendation(resolved.caseId, "customer-foreign")
