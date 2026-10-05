"""Synthetic operator finance, rollback, destination and entitlement regressions."""
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from banking_shared.identity_models import Operator, User
from banking_shared.models import Customer, Product, RuntimePosting, SQLModel, SupportCase, SupportCaseEvent, TransactionRecord
from banking_shared.runtime import effective_balance, project_runtime
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from banking_transaction.services.adjudication import AdjudicationConflict
from banking_transaction.auth.operator_identity import OperatorPrincipal
from banking_transaction.models.operator import AdjudicateRequest, CardProtectionRequest, OperatorCaseDetail
from banking_transaction.services.operator import OperatorCaseService

PRINCIPAL = OperatorPrincipal("operator", 1)


@pytest.fixture
def factory() -> Callable[[], Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        session.add(Customer(customer_id="customer", email="customer@synthetic.invalid"))
        session.add(User(id="operator", email="operator@synthetic.invalid", password_hash="unused", locale="en", status="active"))
        session.flush()
        session.add(Operator(user_id="operator"))
        session.add_all([
            Product(product_id="card", product_number="4111111111111111", customer_id="customer", product_type="Debit Card", currency="USD", current_balance=Decimal("0"), product_status="Active"),
            Product(product_id="savings", product_number="bank-one", customer_id="customer", product_type="Savings Account", currency="USD", current_balance=Decimal("100"), product_status="Active"),
        ])
        session.flush()
        session.add(TransactionRecord(transaction_id="source", transaction_date=now, process_date=now.date(), product_id="card", customer_id="customer", amount=Decimal("12.3456"), currency="USD", transaction_status="Approved"))
        session.flush()
        session.add(SupportCase(case_id="case", customer_id="customer", product_id="card", transaction_id="source", reason="Original reason", status="IN_REVIEW"))
        session.add(SupportCaseEvent(case_id="case", event_type="APPROVAL_GRANTED", actor="customer"))
        session.commit()
    return lambda: Session(engine)


def decision(
    service: OperatorCaseService, verdict: str = "valid", destination: str | None = None,
) -> OperatorCaseDetail:
    case = service.get_case("case", PRINCIPAL)
    return service.adjudicate("case", PRINCIPAL, AdjudicateRequest(verdict=verdict, rationale="Verified original evidence", expected_case_version=case.caseVersion, expected_evidence_version=case.evidenceVersion, destination_product_id=destination))


def test_valid_atomic_posting_preserves_source_and_ingestion_anchor(factory: Callable[[], Session]) -> None:
    service = OperatorCaseService(factory)
    service.claim_case("case", PRINCIPAL)
    result = decision(service)
    assert result.status == "RESOLVED_VALID" and result.effects["amount"] == "12.3456"
    with factory() as session:
        source = session.get(TransactionRecord, "source")
        assert source.amount == Decimal("12.3456") and source.source_kind == "source"
        product = session.get(Product, "savings")
        assert product.current_balance == Decimal("100")
        assert effective_balance(session, product) == Decimal("112.3456")
        movement = session.exec(select(TransactionRecord).where(TransactionRecord.source_kind == "runtime")).one()
        assert movement.original_transaction_id == "source" and movement.support_case_id == "case"
        assert movement.transaction_date >= source.transaction_date
        product.current_balance = Decimal("200")
        session.commit()
        assert effective_balance(session, product) == Decimal("212.3456")
    with pytest.raises(AdjudicationConflict):
        decision(service)
    assert service.get_case("case", PRINCIPAL).effects == result.effects


def test_invalid_terminal_without_financial_effect(factory: Callable[[], Session]) -> None:
    service = OperatorCaseService(factory)
    service.claim_case("case", PRINCIPAL)
    assert decision(service, "invalid").status == "RESOLVED_INVALID"
    with factory() as session:
        assert session.exec(select(RuntimePosting)).all() == []


def test_ambiguous_preferred_tier_requires_owned_destination_and_retry(factory: Callable[[], Session]) -> None:
    with factory() as session:
        session.add_all([
            Product(product_id="savings-two", customer_id="customer", product_type="Savings Account", currency="USD", current_balance=Decimal("5"), product_status="Active"),
            Product(product_id="checking", customer_id="customer", product_type="Checking Account", currency="USD", current_balance=Decimal("9"), product_status="Active"),
        ])
        session.commit()
    service = OperatorCaseService(factory)
    service.claim_case("case", PRINCIPAL)
    pending = decision(service)
    assert pending.status == "PENDING_EFFECTS" and pending.effectCode == "DESTINATION_REQUIRED"
    rejected = service.retry_effects("case", PRINCIPAL, pending.caseVersion, "checking")
    assert rejected.effectCode == "DESTINATION_NOT_ELIGIBLE"
    result = service.retry_effects("case", PRINCIPAL, rejected.caseVersion, "savings-two")
    assert result.status == "RESOLVED_VALID" and result.effects["destinationProductId"] == "savings-two"


def test_effect_failure_rolls_back_posting_movement_audit_and_closure(factory: Callable[[], Session]) -> None:
    service = OperatorCaseService(factory)
    service.claim_case("case", PRINCIPAL)
    with factory() as session:
        engine = session.get_bind()
    def fail(
        connection: object, cursor: object, statement: str, parameters: object,
        context: object, executemany: bool,
    ) -> None:
        if statement.startswith("INSERT INTO runtime_postings"):
            raise IntegrityError(statement, parameters, RuntimeError("synthetic failure"))
    event.listen(engine, "before_cursor_execute", fail)
    try:
        pending = decision(service)
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert pending.status == "PENDING_EFFECTS" and pending.effectCode == "EFFECT_EXECUTION_FAILED"
    with factory() as session:
        assert session.exec(select(RuntimePosting)).all() == []
        assert session.exec(select(TransactionRecord).where(TransactionRecord.source_kind == "runtime")).all() == []
        assert session.exec(select(SupportCaseEvent).where(SupportCaseEvent.event_type == "FINANCIAL_EFFECT_EXECUTED")).all() == []
    assert service.retry_effects("case", PRINCIPAL, pending.caseVersion).status == "RESOLVED_VALID"


def test_failure_after_all_effects_flush_rolls_back_before_commit(
    factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from banking_transaction.services import operator as operator_service
    service = OperatorCaseService(factory)
    service.claim_case("case", PRINCIPAL)
    original_execute = operator_service.execute_effects

    def fail_after_flush(
        session: Session, case: SupportCase, principal: OperatorPrincipal,
        destination_id: str | None,
    ) -> None:
        original_execute(session, case, principal, destination_id)
        assert case.status == "RESOLVED_VALID"
        assert session.get(RuntimePosting, "source") is not None
        raise IntegrityError("synthetic precommit failure", {}, RuntimeError("rollback"))

    monkeypatch.setattr(operator_service, "execute_effects", fail_after_flush)
    pending = decision(service)
    assert pending.status == "PENDING_EFFECTS"
    assert pending.effectCode == "EFFECT_EXECUTION_FAILED"
    with factory() as session:
        assert session.get(RuntimePosting, "source") is None
        assert session.exec(select(TransactionRecord).where(
            TransactionRecord.source_kind == "runtime",
        )).all() == []
        assert session.exec(select(SupportCaseEvent).where(
            SupportCaseEvent.event_type == "FINANCIAL_EFFECT_EXECUTED",
        )).all() == []
        case = session.get(SupportCase, "case")
        assert case is not None and case.resolved_at is None
        assert case.verdict == "valid"
        product = session.get(Product, "savings")
        assert product is not None and effective_balance(session, product) == Decimal("100")
    monkeypatch.setattr(operator_service, "execute_effects", original_execute)
    assert service.retry_effects("case", PRINCIPAL, pending.caseVersion).status == "RESOLVED_VALID"


def test_failed_attempt_does_not_overwrite_a_newer_successful_retry(
    factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from banking_transaction.services import operator as operator_service
    service = OperatorCaseService(factory)
    service.claim_case("case", PRINCIPAL)
    original_execute = operator_service.execute_effects

    def fail_after_another_retry_succeeds(
        session: Session, case: SupportCase, principal: OperatorPrincipal,
        destination_id: str | None,
    ) -> None:
        case_id, version = case.case_id, case.case_version
        session.rollback()
        monkeypatch.setattr(operator_service, "execute_effects", original_execute)
        success = OperatorCaseService(factory).retry_effects(case_id, principal, version)
        assert success.status == "RESOLVED_VALID"
        raise IntegrityError("delayed failure", {}, RuntimeError("older attempt"))

    monkeypatch.setattr(operator_service, "execute_effects", fail_after_another_retry_succeeds)
    result = decision(service)
    assert result.status == "RESOLVED_VALID" and result.effectCode is None
    with factory() as session:
        assert len(session.exec(select(RuntimePosting)).all()) == 1
        assert len(session.exec(select(SupportCaseEvent).where(
            SupportCaseEvent.event_type == "FINANCIAL_EFFECT_EXECUTED",
        )).all()) == 1


def test_version_owner_evidence_and_separate_card_protection(factory: Callable[[], Session]) -> None:
    service = OperatorCaseService(factory)
    claimed = service.claim_case("case", PRINCIPAL)
    with pytest.raises(AdjudicationConflict, match="CASE_VERSION_CONFLICT"):
        service.retry_effects("case", PRINCIPAL, 0)
    with pytest.raises(AdjudicationConflict, match="OPERATOR_UNAVAILABLE"):
        service.protect_card("case", OperatorPrincipal("other", 1), CardProtectionRequest(expected_case_version=claimed.caseVersion, rationale="Protect", blocked=True))
    protected = service.protect_card("case", PRINCIPAL, CardProtectionRequest(expected_case_version=claimed.caseVersion, rationale="Customer evidence indicates risk", blocked=True))
    assert protected.status == "IN_REVIEW" and protected.effects is None
    with factory() as session:
        assert project_runtime(session, session.get(Product, "card")).product_status == "Blocked"
    assert decision(service, "invalid").cardProtection["blocked"] is True


def test_lifetime_entitlement_and_active_case_unique(factory: Callable[[], Session]) -> None:
    service = OperatorCaseService(factory)
    service.claim_case("case", PRINCIPAL)
    with factory() as session:
        session.add(SupportCase(case_id="duplicate", transaction_id="source", product_id="card", customer_id="customer", reason="Duplicate", status="IN_REVIEW"))
        with pytest.raises(IntegrityError):
            session.commit()
    decision(service)
    with factory() as session:
        session.add(SupportCase(case_id="second", transaction_id="source", product_id="card", customer_id="customer", reason="Again", status="IN_REVIEW"))
        session.add(SupportCaseEvent(case_id="second", event_type="APPROVAL_GRANTED", actor="customer"))
        session.commit()
    second = service.claim_case("second", PRINCIPAL)
    result = service.adjudicate("second", PRINCIPAL, AdjudicateRequest(verdict="valid", rationale="Second adjudication", expected_case_version=second.caseVersion, expected_evidence_version=second.evidenceVersion))
    assert result.status == "PENDING_EFFECTS" and result.effectCode == "CREDIT_ALREADY_APPLIED"
    with factory() as session:
        assert len(session.exec(select(RuntimePosting)).all()) == 1


@pytest.mark.parametrize("ineligible", ["foreign", "inactive", "currency"])
def test_destination_filter_falls_back_to_checking(
    factory: Callable[[], Session], ineligible: str,
) -> None:
    with factory() as session:
        savings = session.get(Product, "savings")
        assert savings is not None
        if ineligible == "foreign":
            session.add(Customer(customer_id="foreign", email="foreign@synthetic.invalid"))
            session.flush()
            savings.customer_id = "foreign"
        elif ineligible == "inactive":
            savings.product_status = "Inactive"
        else:
            savings.currency = "EUR"
        session.add(Product(
            product_id="checking", customer_id="customer", product_type="Checking Account",
            currency="USD", current_balance=Decimal("10"), product_status="Active",
        ))
        session.add(savings)
        session.commit()
    service = OperatorCaseService(factory)
    service.claim_case("case", PRINCIPAL)
    rejected = decision(service, destination="savings")
    assert rejected.status == "PENDING_EFFECTS"
    assert rejected.effectCode == "DESTINATION_NOT_ELIGIBLE"
    result = service.retry_effects("case", PRINCIPAL, rejected.caseVersion)
    assert result.status == "RESOLVED_VALID"
    assert result.effects is not None and result.effects["destinationProductId"] == "checking"


@pytest.mark.parametrize("balance", [None, Decimal("100")])
def test_credit_card_restitution_reduces_positive_debt_or_stays_pending(
    factory: Callable[[], Session], balance: Decimal | None,
) -> None:
    with factory() as session:
        card = session.get(Product, "card")
        assert card is not None
        card.product_type = "Credit Card"
        card.current_balance = balance
        session.add(card)
        session.commit()
    service = OperatorCaseService(factory)
    service.claim_case("case", PRINCIPAL)
    result = decision(service)
    if balance is None:
        assert result.status == "PENDING_EFFECTS" and result.effectCode == "EVIDENCE_UNAVAILABLE"
        assert result.effects is None
    else:
        assert result.status == "RESOLVED_VALID" and result.effects is not None
        assert result.effects["balanceDelta"] == "-12.3456"
        with factory() as session:
            card = session.get(Product, "card")
            assert card is not None
            assert effective_balance(session, card) == Decimal("87.6544")


def test_persisted_other_operator_cannot_adjudicate_or_protect(
    factory: Callable[[], Session],
) -> None:
    with factory() as session:
        session.add(User(
            id="other", email="other@synthetic.invalid", password_hash="unused", status="active",
            locale="en",
        ))
        session.flush()
        session.add(Operator(user_id="other"))
        session.commit()
    service = OperatorCaseService(factory)
    claimed = service.claim_case("case", PRINCIPAL)
    other = OperatorPrincipal("other", 1)
    with pytest.raises(LookupError):
        service.adjudicate("case", other, AdjudicateRequest(
            verdict="valid", rationale="Foreign operator", expected_case_version=claimed.caseVersion,
            expected_evidence_version=claimed.evidenceVersion,
        ))
    with pytest.raises(LookupError):
        service.protect_card("case", other, CardProtectionRequest(
            expected_case_version=claimed.caseVersion, rationale="Foreign operator", blocked=True,
        ))
    assert service.get_case("case", PRINCIPAL).verdict is None


def test_evidence_drift_requires_refresh_without_recording_verdict(
    factory: Callable[[], Session],
) -> None:
    service = OperatorCaseService(factory)
    claimed = service.claim_case("case", PRINCIPAL)
    with factory() as session:
        source = session.get(TransactionRecord, "source")
        assert source is not None
        source.amount = Decimal("15")
        session.add(source)
        session.commit()
    with pytest.raises(AdjudicationConflict, match="EVIDENCE_VERSION_CONFLICT"):
        service.adjudicate("case", PRINCIPAL, AdjudicateRequest(
            verdict="valid", rationale="Stale evidence", expected_case_version=claimed.caseVersion,
            expected_evidence_version=claimed.evidenceVersion,
        ))
    refreshed = service.get_case("case", PRINCIPAL)
    assert refreshed.verdict is None and refreshed.status == "IN_REVIEW"
    assert refreshed.evidenceVersion == claimed.evidenceVersion + 1
    assert refreshed.caseVersion == claimed.caseVersion + 1
    assert decision(service).effects["amount"] == "15.0000"


def test_missing_customer_consent_cannot_adjudicate(factory: Callable[[], Session]) -> None:
    service = OperatorCaseService(factory)
    claimed = service.claim_case("case", PRINCIPAL)
    with factory() as session:
        consent = session.exec(select(SupportCaseEvent).where(
            SupportCaseEvent.event_type == "APPROVAL_GRANTED",
        )).one()
        session.delete(consent)
        session.commit()
    with pytest.raises(AdjudicationConflict, match="CASE_CONSENT_REQUIRED"):
        service.adjudicate("case", PRINCIPAL, AdjudicateRequest(
            verdict="invalid", rationale="No consent", expected_case_version=claimed.caseVersion,
            expected_evidence_version=claimed.evidenceVersion,
        ))
    assert service.get_case("case", PRINCIPAL).verdict is None


@pytest.mark.parametrize("product_type", ["Debit Card", "Credit Card"])
def test_generated_refund_is_not_disputable(
    factory: Callable[[], Session], product_type: str,
) -> None:
    from banking_transaction.services.disputes import CardOnlyDisputeError, SupportCaseService

    with factory() as session:
        card = session.get(Product, "card")
        assert card is not None
        card.product_type = product_type
        session.add(card)
        session.commit()
    service = OperatorCaseService(factory)
    service.claim_case("case", PRINCIPAL)
    result = decision(service)
    assert result.effects is not None
    with pytest.raises(CardOnlyDisputeError):
        SupportCaseService(factory).open_transaction_dispute(
            result.effects["movementId"], "customer", "Refund dispute",
        )


def test_customer_reads_recorded_effect_and_protection_references(factory: Callable[[], Session]) -> None:
    from banking_transaction.services.disputes import SupportCaseService

    operator = OperatorCaseService(factory)
    claimed = operator.claim_case("case", PRINCIPAL)
    assert claimed.productProtectionStatus == "Active"
    customers = SupportCaseService(factory)
    initial = customers.get_case("case", "customer")
    assert initial.effects is None and initial.verdict is None
    assert initial.rationale is None and initial.cardProtection is None
    resolved = decision(operator)
    protected = operator.protect_card("case", PRINCIPAL, CardProtectionRequest(
        expected_case_version=resolved.caseVersion, rationale="Recorded local risk", blocked=True,
    ))
    customer = customers.get_case("case", "customer")
    assert customer.effects == resolved.effects
    assert customer.effects["amount"] == "12.3456"
    assert customer.effects["balanceDelta"] == "12.3456"
    assert customer.effects["movementId"] and customer.effects["executedAt"]
    assert customer.caseVersion == protected.caseVersion
    assert customer.verdict == "valid" and customer.rationale == "Verified original evidence"
    assert customer.reason == "Original reason"
    assert customer.cardProtection == protected.cardProtection
    assert customer.cardProtection["priorStatus"] == "Active"
    assert customer.cardProtection["scope"] == "LOCAL_PRODUCT_ONLY"
    assert protected.productProtectionStatus == "Blocked"
    with pytest.raises(PermissionError):
        customers.get_case("case", "other")


@pytest.mark.parametrize("status", ["RESOLVED_INVALID", "RESOLVED"])
def test_customer_terminal_reads_do_not_invent_effects(
    factory: Callable[[], Session], status: str,
) -> None:
    from banking_transaction.services.disputes import SupportCaseService

    with factory() as session:
        case = session.get(SupportCase, "case")
        case.status = status
        session.commit()
    customer = SupportCaseService(factory).get_case("case", "customer")
    assert customer.effects is None and customer.cardProtection is None
    assert customer.financialEffectsStatus == "NOT_EXECUTED"


def test_product_protection_state_preserves_unknown_prior_status(factory: Callable[[], Session]) -> None:
    from banking_transaction.services.disputes import SupportCaseService

    with factory() as session:
        product = session.get(Product, "card")
        product.product_status = None
        session.commit()
    operator = OperatorCaseService(factory)
    claimed = operator.claim_case("case", PRINCIPAL)
    assert claimed.productProtectionStatus is None
    protected = operator.protect_card("case", PRINCIPAL, CardProtectionRequest(
        expected_case_version=claimed.caseVersion, rationale="Local risk", blocked=True,
    ))
    assert protected.productProtectionStatus == "Blocked"
    assert protected.cardProtection["priorStatus"] is None
    customer = SupportCaseService(factory).get_case("case", "customer")
    assert customer.cardProtection["priorStatus"] is None
    released = operator.protect_card("case", PRINCIPAL, CardProtectionRequest(
        expected_case_version=protected.caseVersion, rationale="Local risk cleared", blocked=False,
    ))
    assert released.productProtectionStatus is None
    assert released.cardProtection["blocked"] is False
