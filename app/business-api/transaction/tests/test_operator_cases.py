"""Synthetic consent, ownership, exclusive takeover and atomic audit regressions."""
from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from banking_shared.models import SQLModel, SupportCase, SupportCaseEvent
from banking_shared.identity_models import User, Operator
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

import operator_routers
from operator_identity import OperatorPrincipal, get_operator_principal
from operator_service import OperatorCaseService, OperatorClaimConflict

OPERATOR = OperatorPrincipal("operator-one", 3)
OTHER = OperatorPrincipal("operator-two", 1)


@pytest.fixture
def factory() -> Callable[[], Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for subject in ("operator-one", "operator-two"):
            session.add(User(
                id=subject, email=f"{subject}@synthetic.invalid",
                password_hash="unused-test-hash", locale="en", status="active",
            ))
        session.flush()
        session.add_all([Operator(user_id="operator-one"), Operator(user_id="operator-two")])
        session.flush()
        for index, (status, consent, owner) in enumerate([
            ("IN_REVIEW", True, None), ("IN_REVIEW", True, None),
            ("IN_REVIEW", False, None), ("WAITING_USER_APPROVAL", True, None),
            ("RESOLVED", True, None), ("IN_REVIEW", True, OTHER.sub),
        ]):
            case = SupportCase(case_id=f"case-{index}", customer_id="customer-sensitive",
                               product_id="product", transaction_id="transaction", reason="Sensitive reason",
                               status=status, legacy_assigned_agent_id="historical-catalog",
                               assigned_operator_sub=owner,
                               opened_at=datetime(2026, 1, index + 1, tzinfo=timezone.utc))
            session.add(case)
            if consent:
                session.add(SupportCaseEvent(case_id=case.case_id, event_type="APPROVAL_GRANTED",
                                             actor="customer"))
        session.commit()
    return lambda: Session(engine)


def test_queue_filters_and_limits_sensitive_fields(factory: Callable[[], Session]) -> None:
    service = OperatorCaseService(factory)
    page = service.list_cases(OPERATOR, offset=1, limit=1)
    assert page.total == 2 and page.offset == 1 and page.limit == 1
    assert [case.caseId for case in page.items] == ["case-1"]
    assert set(page.items[0].model_dump()) == {
        "caseId", "status", "openedAt", "updatedAt", "triageOutcome", "claimVersion",
    }


def test_assigned_listing_isolates_exact_operator_ownership(factory: Callable[[], Session]) -> None:
    service = OperatorCaseService(factory)
    assert service.list_cases(OPERATOR, view="assigned").items == []
    with factory() as session:
        case = session.get(SupportCase, "case-2")
        assert case is not None
        case.assigned_operator_sub = OPERATOR.sub
        case.claimed_at = datetime.now(timezone.utc)
        session.commit()
    page = service.list_cases(OPERATOR, view="assigned")
    assert page.total == 1
    assert [case.caseId for case in page.items] == ["case-2"]
    assert [case.caseId for case in service.list_cases(OTHER, view="assigned").items] == ["case-5"]
    assert service.list_cases(OperatorPrincipal("operator-one-prefix", 3), view="assigned").total == 0
    assert set(page.model_dump()) == {"items", "total", "offset", "limit"}
    assert set(page.items[0].model_dump()) == {
        "caseId", "status", "openedAt", "updatedAt", "triageOutcome", "claimVersion",
    }


def test_assigned_listing_pagination_and_stable_order(factory: Callable[[], Session]) -> None:
    service = OperatorCaseService(factory)
    service.claim_case("case-1", OPERATOR)
    service.claim_case("case-0", OPERATOR)
    with factory() as session:
        first = session.get(SupportCase, "case-0")
        second = session.get(SupportCase, "case-1")
        assert first is not None and second is not None
        second.opened_at = first.opened_at
        session.commit()
    first_page = service.list_cases(OPERATOR, limit=1, view="assigned")
    second_page = service.list_cases(OPERATOR, offset=1, limit=1, view="assigned")
    assert [case.caseId for case in first_page.items] == ["case-0"]
    assert [case.caseId for case in second_page.items] == ["case-1"]
    assert first_page.total == second_page.total == 2
    assert (second_page.offset, second_page.limit) == (1, 1)
    beyond_end = service.list_cases(OPERATOR, offset=2, limit=1, view="assigned")
    assert beyond_end.items == [] and beyond_end.total == 2


def test_claim_moves_case_between_views_and_resolution_remains_discoverable(
    factory: Callable[[], Session],
) -> None:
    service = OperatorCaseService(factory)
    assert [case.caseId for case in service.list_cases(OPERATOR).items] == ["case-0", "case-1"]
    service.claim_case("case-0", OPERATOR)
    assert [case.caseId for case in service.list_cases(OPERATOR, view="available").items] == ["case-1"]
    assert [case.caseId for case in service.list_cases(OPERATOR, view="assigned").items] == ["case-0"]
    with factory() as session:
        case = session.get(SupportCase, "case-0")
        assert case is not None
        case.status = "RESOLVED"
        case.resolved_at = datetime.now(timezone.utc)
        session.commit()
    page = service.list_cases(OPERATOR, view="assigned")
    assert page.total == 1 and page.items[0].caseId == "case-0"
    assert page.items[0].status == "RESOLVED"
    assert service.get_case("case-0", OPERATOR).status == "RESOLVED"
    assert service.list_cases(OPERATOR).total == 1
    assert [case.caseId for case in service.list_cases(OTHER, view="assigned").items] == ["case-5"]


def test_claim_exclusive_owned_detail_and_audit(factory: Callable[[], Session]) -> None:
    service = OperatorCaseService(factory)
    claimed = service.claim_case("case-0", OPERATOR)
    assert claimed.assignedOperatorSub == OPERATOR.sub and claimed.claimVersion == 1
    assert claimed.status == "IN_REVIEW" and claimed.claimedAt
    assert service.get_case("case-0", OPERATOR) == claimed
    assert service.list_cases(OPERATOR).total == 1
    for principal in (OPERATOR, OTHER):
        with pytest.raises(OperatorClaimConflict):
            service.claim_case("case-0", principal)
    with pytest.raises(LookupError):
        service.get_case("case-0", OTHER)
    with factory() as session:
        case = session.get(SupportCase, "case-0")
        assert case is not None and case.legacy_assigned_agent_id == "historical-catalog"
        assert case.resolution_outcome is None and case.resolved_at is None
        audit = session.exec(select(SupportCaseEvent).where(
            SupportCaseEvent.event_type == "OPERATOR_CLAIMED",
        )).one()
        assert (audit.actor, audit.operator_sub, audit.operator_identity_version, audit.claim_version) == (
            "operator", OPERATOR.sub, 3, 1,
        )


@pytest.mark.parametrize("case_id", ["missing", "case-2", "case-3", "case-4", "case-5"])
def test_ineligible_claim_and_unguarded_detail_rejected(factory: Callable[[], Session], case_id: str) -> None:
    service = OperatorCaseService(factory)
    with pytest.raises(OperatorClaimConflict):
        service.claim_case(case_id, OPERATOR)
    with pytest.raises(LookupError):
        service.get_case(case_id, OPERATOR)


def test_claim_rolls_back_if_audit_fails(factory: Callable[[], Session]) -> None:
    def fail_audit(session: Session, context: object, instances: object) -> None:
        if any(isinstance(item, SupportCaseEvent) and item.event_type == "OPERATOR_CLAIMED"
               for item in session.new):
            raise RuntimeError("Synthetic audit failure")
    event.listen(Session, "before_flush", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="Synthetic audit failure"):
            OperatorCaseService(factory).claim_case("case-0", OPERATOR)
    finally:
        event.remove(Session, "before_flush", fail_audit)
    with factory() as session:
        case = session.get(SupportCase, "case-0")
        assert case is not None and case.assigned_operator_sub is None
        assert case.claimed_at is None and case.claim_version == 0


def test_rest_contract_and_conflict_codes(factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(operator_routers, "service", OperatorCaseService(factory))
    app = FastAPI()
    app.include_router(operator_routers.router, prefix="/api/operator/support-cases")
    app.dependency_overrides[get_operator_principal] = lambda: OPERATOR
    with TestClient(app) as client:
        prefix = "/api/operator/support-cases"
        assert client.get(prefix).json()["total"] == 2
        assert client.get(prefix + "?limit=101").status_code == 422
        assert client.get(prefix + "?view=invalid").status_code == 422
        assert client.get(prefix + "?view=assigned").json() == {
            "items": [], "total": 0, "offset": 0, "limit": 50,
        }
        assert client.get(prefix + "/case-0").json() == {"detail": {"code": "CASE_NOT_FOUND"}}
        response = client.post(prefix + "/case-0/claim")
        assert response.status_code == 200 and response.json()["claimVersion"] == 1
        assigned_response = client.get(prefix + "?view=assigned&offset=0&limit=1")
        assert assigned_response.status_code == 200
        assigned = assigned_response.json()
        assert assigned["total"] == 1 and assigned["offset"] == 0 and assigned["limit"] == 1
        assert [case["caseId"] for case in assigned["items"]] == ["case-0"]
        assert set(assigned["items"][0]) == {
            "caseId", "status", "openedAt", "updatedAt", "triageOutcome", "claimVersion",
        }
        assert [case["caseId"] for case in client.get(prefix).json()["items"]] == ["case-1"]
        assert client.get(prefix + "/case-0").status_code == 200
        response = client.post(prefix + "/case-0/claim")
        assert response.status_code == 409
        assert response.json() == {"detail": {"code": "OPERATOR_CLAIM_CONFLICT"}}
        assert client.post(prefix + "/case-0/resolve").status_code == 404


def test_claim_missing_persisted_operator_fails_without_mutation(
    factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operator_routers, "service", OperatorCaseService(factory))
    app = FastAPI()
    app.include_router(operator_routers.router, prefix="/api/operator/support-cases")
    app.dependency_overrides[get_operator_principal] = lambda: OperatorPrincipal("absent", 1)
    with TestClient(app) as client:
        response = client.post("/api/operator/support-cases/case-0/claim")
        assert response.status_code == 503
        assert response.json() == {"detail": {"code": "SERVICE_UNAVAILABLE"}}
    with factory() as session:
        case = session.get(SupportCase, "case-0")
        assert case is not None and case.assigned_operator_sub is None
        assert case.claim_version == 0 and case.claimed_at is None
        assert session.exec(select(SupportCaseEvent).where(
            SupportCaseEvent.event_type == "OPERATOR_CLAIMED",
        )).all() == []
