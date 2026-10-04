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
    SupportCaseEvent,
    TransactionRecord,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

import dispute_routers
from dispute_service import CardOnlyDisputeError, SupportCaseService
from jwt_identity import get_jwt_customer_id

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


@pytest.mark.parametrize("product_type", ["Checking Account", "Savings Account"])
def test_account_dispute_rejected_without_writes_and_legacy_cases_readable(
    session_factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch,
    product_type: str,
) -> None:
    with session_factory() as session:
        product = session.get(Product, "card-owned")
        assert product is not None
        product.product_type = product_type
        session.add(product)
        session.commit()
    service = SupportCaseService(session_factory)
    with pytest.raises(CardOnlyDisputeError):
        service.open_transaction_dispute("tx-low-risk", "customer-owned", "Unrecognized")
    monkeypatch.setattr(dispute_routers, "service", service)
    app = FastAPI()
    app.include_router(dispute_routers.router, prefix="/api/support-cases")
    app.dependency_overrides[get_jwt_customer_id] = lambda: "customer-owned"
    with TestClient(app) as client:
        response = client.post("/api/support-cases", json={
            "transactionId": "tx-low-risk", "reason": "Unrecognized",
        })
    assert response.status_code == 400
    assert response.json() == {"detail": {"code": "DISPUTE_CARD_ONLY"}}
    with session_factory() as session:
        assert session.exec(select(SupportCase)).all() == []
        assert session.exec(select(SupportCaseEvent)).all() == []
        historical = SupportCase(
            customer_id="customer-owned", product_id="card-owned",
            transaction_id="tx-low-risk", reason="Historical account case",
            status="WAITING_USER_APPROVAL",
        )
        session.add(historical)
        session.commit()
        session.refresh(historical)
        case_id = historical.case_id
    assert service.get_case(case_id, "customer-owned").reason == "Historical account case"
    assert [case.caseId for case in service.list_cases("customer-owned")] == [case_id]
    assert service.get_case_timeline(case_id, "customer-owned") == []
    with pytest.raises(PermissionError):
        service.get_case(case_id, "customer-foreign")


@pytest.mark.parametrize("product_type", ["Debit Card", "Credit Card"])
def test_new_disputes_accept_both_card_types(
    session_factory: Callable[[], Session], product_type: str,
) -> None:
    with session_factory() as session:
        product = session.get(Product, "card-owned")
        assert product is not None
        product.product_type = product_type
        session.add(product)
        session.commit()
    opened = SupportCaseService(session_factory).open_transaction_dispute(
        "tx-low-risk", "customer-owned", "Unrecognized",
    )
    assert opened.status == "WAITING_USER_APPROVAL"


def test_duplicate_route_returns_controlled_conflict(
    session_factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SupportCaseService(session_factory)
    monkeypatch.setattr(dispute_routers, "service", service)
    app = FastAPI()
    app.include_router(dispute_routers.router, prefix="/api/support-cases")
    app.dependency_overrides[get_jwt_customer_id] = lambda: "customer-owned"
    payload = {"transactionId": "tx-low-risk", "reason": "Unrecognized charge"}

    with TestClient(app) as client:
        created = client.post("/api/support-cases", json=payload)
        assert created.status_code == 201
        duplicate = client.post("/api/support-cases", json=payload)
        assert duplicate.status_code == 409
        assert duplicate.json() == {"detail": {"code": "DISPUTE_ALREADY_ACTIVE"}}
        assert len(service.list_cases("customer-owned")) == 1


@pytest.mark.parametrize("transaction_id", ["tx-foreign", "tx-missing"])
def test_open_route_preserves_resource_denial(
    session_factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch,
    transaction_id: str,
) -> None:
    monkeypatch.setattr(dispute_routers, "service", SupportCaseService(session_factory))
    app = FastAPI()
    app.include_router(dispute_routers.router, prefix="/api/support-cases")
    app.dependency_overrides[get_jwt_customer_id] = lambda: "customer-owned"

    with TestClient(app) as client:
        response = client.post(
            "/api/support-cases",
            json={"transactionId": transaction_id, "reason": "Unrecognized charge"},
        )
        assert response.status_code == 403


def test_low_fraud_score_case_stays_in_review_until_explicit_resolution(
    session_factory: Callable[[], Session],
) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-low-risk", "customer-owned", "No reconozco este cargo")
    assert opened.status == "WAITING_USER_APPROVAL"
    assert opened.productNumber == "**** 1111"

    resolved = service.respond_to_approval(opened.caseId, "customer-owned", approved=True)

    assert resolved.status == "IN_REVIEW"
    assert resolved.triageOutcome == "fast_track"
    assert resolved.resolutionOutcome is None
    assert resolved.resolvedAt is None
    assert resolved.recommendationType is None
    assert service.get_case(opened.caseId, "customer-owned") == resolved
    assert resolved.financialEffectsStatus == "NOT_IMPLEMENTED"
    assert resolved.cardProtectionStatus == "NOT_IMPLEMENTED"
    assert "workflowMode" not in resolved.model_dump()
    timeline = service.get_case_timeline(opened.caseId, "customer-owned")
    assert all("simulat" not in event.displayMessage.lower() for event in timeline)
    assert [event.eventType for event in timeline] == [
        "CASE_OPENED", "APPROVAL_REQUESTED", "APPROVAL_GRANTED", "REVIEW_REQUIRED",
    ]
    with session_factory() as session:
        assert session.get(SupportCase, opened.caseId).assigned_agent_id == "agent-1"
        assert session.get(Product, "card-owned").product_status == "Active"
        assert session.get(TransactionRecord, "tx-low-risk").amount == Decimal("120.0000")

    explicitly_resolved = service.resolve_case(
        opened.caseId, "customer-owned", "no_fraud_found", "Explicit review decision",
    )
    assert explicitly_resolved.status == "RESOLVED"
    assert explicitly_resolved.resolutionOutcome == "no_fraud_found"
    assert explicitly_resolved.resolvedAt is not None
    assert service.get_case(opened.caseId, "customer-owned") == explicitly_resolved


@pytest.mark.parametrize(
    ("event_type", "actor", "message", "projected"),
    [
        ("RESOLVED", "system",
         "Provisional credit issued; case resolved without manual review", True),
        ("RESOLVED", "agent", "Case resolved: fraud_confirmed_refund_issued", True),
        ("ESCALATED_TO_REVIEW", "system",
         "Elevated fraud-risk score; routed to manual review (assigned to agent agent-1)", True),
        ("ESCALATED_TO_REVIEW", "system",
         "No fraud score available for this transaction; routed to manual review (no agent available)",
         True),
        ("ESCALATED_TO_REVIEW", "system",
         "Elevated fraud-risk score; routed to manual review: custom note", False),
        ("RESOLVED", "agent", "Reviewed by agent-1", False),
        ("RESOLVED", "customer",
         "Provisional credit issued; case resolved without manual review", False),
    ],
)
def test_historical_timeline_projects_only_known_generated_messages(
    session_factory: Callable[[], Session],
    event_type: str,
    actor: str,
    message: str,
    projected: bool,
) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-low-risk", "customer-owned", "Reclamo")
    with session_factory() as session:
        session.add(SupportCaseEvent(
            case_id=opened.caseId, event_type=event_type, actor=actor, message=message,
        ))
        session.commit()
    event = service.get_case_timeline(opened.caseId, "customer-owned")[-1]
    assert event.message == message
    assert (event.displayMessage != message) is projected
    if projected:
        assert "simulat" not in event.displayMessage.lower()
        assert "no " in event.displayMessage
    with session_factory() as session:
        stored = session.exec(select(SupportCaseEvent).where(
            SupportCaseEvent.case_id == opened.caseId,
            SupportCaseEvent.message == message,
        )).one()
        assert stored.message == message


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


@pytest.mark.parametrize("transaction_id", ["tx-low-risk", "tx-high-risk", "tx-no-score"])
def test_approval_without_catalog_reviewer_remains_unresolved(
    session_factory: Callable[[], Session], transaction_id: str,
) -> None:
    with session_factory() as session:
        for agent in session.exec(select(ServiceAgent)).all():
            session.delete(agent)
        session.commit()

    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute(transaction_id, "customer-owned", "Unrecognized charge")
    reviewing = service.respond_to_approval(opened.caseId, "customer-owned", approved=True)

    assert reviewing.status == "IN_REVIEW"
    assert reviewing.resolutionOutcome is None
    assert reviewing.resolvedAt is None
    assert reviewing.recommendationType is None
    with session_factory() as session:
        assert session.get(SupportCase, opened.caseId).assigned_agent_id is None
    assert "RESOLVED" not in [
        event.eventType for event in service.get_case_timeline(opened.caseId, "customer-owned")
    ]


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


def test_low_risk_case_gets_a_recommendation_only_after_explicit_resolution(
    session_factory: Callable[[], Session],
) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-low-risk", "customer-owned", "Reclamo")

    reviewing = service.respond_to_approval(opened.caseId, "customer-owned", approved=True)
    assert reviewing.recommendationType is None
    resolved = service.resolve_case(opened.caseId, "customer-owned", "fraud_confirmed_refund_issued")

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
    service.respond_to_approval(opened.caseId, "customer-owned", approved=True)
    resolved = service.resolve_case(opened.caseId, "customer-owned", "fraud_confirmed_refund_issued")

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
    service.respond_to_approval(opened.caseId, "customer-owned", approved=True)
    resolved = service.resolve_case(opened.caseId, "customer-owned", "fraud_confirmed_refund_issued")

    with pytest.raises(PermissionError, match="authenticated customer"):
        service.dismiss_recommendation(resolved.caseId, "customer-foreign")


@pytest.mark.parametrize("score,outcome", [
    (Decimal("31.9999"), "fast_track"), (Decimal("32"), "escalated"),
])
def test_triage_threshold_boundary(
    session_factory: Callable[[], Session], score: Decimal, outcome: str,
) -> None:
    with session_factory() as session:
        transaction = session.get(TransactionRecord, "tx-low-risk")
        assert transaction is not None
        transaction.fraud_score = score
        session.add(transaction)
        session.commit()
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-low-risk", "customer-owned", "Unrecognized charge")
    result = service.respond_to_approval(opened.caseId, "customer-owned", approved=True)
    assert result.triageOutcome == outcome
    assert result.status == "IN_REVIEW"
    assert result.resolutionOutcome is None
    assert result.recommendationType is None


@pytest.mark.parametrize("transaction_id", ["tx-low-risk", "tx-high-risk"])
@pytest.mark.parametrize("approved", [True, False])
def test_repeated_approval_cannot_mutate_resolved_or_review_case(
    session_factory: Callable[[], Session], transaction_id: str, approved: bool,
) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute(transaction_id, "customer-owned", "Unrecognized charge")
    original = service.respond_to_approval(opened.caseId, "customer-owned", approved=True)
    events = service.get_case_timeline(opened.caseId, "customer-owned")
    with pytest.raises(ValueError, match="not awaiting approval"):
        service.respond_to_approval(opened.caseId, "customer-owned", approved=approved)
    assert service.get_case(opened.caseId, "customer-owned") == original
    assert service.get_case_timeline(opened.caseId, "customer-owned") == events


def test_foreign_timeline_and_resolution_are_denied_without_mutation(
    session_factory: Callable[[], Session],
) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-high-risk", "customer-owned", "Unrecognized charge")
    original = service.respond_to_approval(opened.caseId, "customer-owned", approved=True)
    with pytest.raises(PermissionError, match="authenticated customer"):
        service.get_case_timeline(opened.caseId, "customer-foreign")
    with pytest.raises(PermissionError, match="authenticated customer"):
        service.resolve_case(opened.caseId, "customer-foreign", "fraud_confirmed_refund_issued")
    assert service.get_case(opened.caseId, "customer-owned") == original


def test_resolution_and_optout_timeline_matches_service_transitions(
    session_factory: Callable[[], Session],
) -> None:
    service = SupportCaseService(session_factory)
    opened = service.open_transaction_dispute("tx-high-risk", "customer-owned", "Unrecognized charge")
    service.respond_to_approval(opened.caseId, "customer-owned", approved=True)
    service.resolve_case(opened.caseId, "customer-owned", "fraud_confirmed_refund_issued")
    service.dismiss_recommendation(opened.caseId, "customer-owned")
    assert [event.eventType for event in service.get_case_timeline(opened.caseId, "customer-owned")] == [
        "CASE_OPENED", "APPROVAL_REQUESTED", "APPROVAL_GRANTED", "ESCALATED_TO_REVIEW",
        "RESOLVED", "RECOMMENDATION_DISMISSED",
    ]
