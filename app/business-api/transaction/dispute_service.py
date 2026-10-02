"""Persisted transaction-dispute support-case workflow.

State machine: OPEN -> WAITING_USER_APPROVAL -> IN_REVIEW -> RESOLVED. The AI agent
only performs intake/triage; it never decides a dispute's legitimacy. Deterministic
triage uses fraud_score (populated at ingestion, never computed by the agent) to
fast-track low-risk cases and escalate higher-risk ones to a simulated human reviewer
drawn from the existing ServiceAgent table. See
app/business-api/data/scripts/evaluate_fraud_threshold.py for the threshold's offline
precision/recall evidence.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from banking_shared.database import create_session
from banking_shared.models import (
    Product,
    ServiceAgent,
    SupportCase,
    SupportCaseEvent,
    TransactionRecord,
)
from banking_shared.product_types import CARD_PRODUCT_TYPES
from models import DisputeCase, DisputeCaseEvent
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

# fraud_score is a 0-100 scale (not [0,1]); >=32 reaches precision 1.0 / recall 0.668 /
# F1 0.801 against the dataset's own is_fraud label (see evaluate_fraud_threshold.py).
FRAUD_SCORE_ESCALATION_THRESHOLD = Decimal("32")

# Mock policy: compresses a real-world multi-week dispute investigation window for the
# demo. Stated explicitly here rather than implied as a dataset-derived rule.
DISPUTE_WINDOW_DAYS = 90

DISPUTABLE_TRANSACTION_STATUS = "Approved"
ACTIVE_PRODUCT_STATUS = "Active"
REVIEW_AGENT_SPECIALTY = "Fraudes"
REVIEW_AGENT_STATUS = "Active"

TRIAGE_FAST_TRACK = "fast_track"
TRIAGE_ESCALATED = "escalated"
TRIAGE_INSUFFICIENT_SIGNAL = "insufficient_signal"

# Resolution outcomes that count as the dispute being ruled in the customer's favor.
# A recommendation is only generated for these; a withdrawn or declined case gets none.
FAVORABLE_RESOLUTION_OUTCOMES = {"fast_tracked_provisional_credit", "fraud_confirmed_refund_issued"}

# Single guardrailed post-resolution recommendation: suggest enabling transaction
# alerts, the one product feature directly relevant to a resolved fraud dispute.
RECOMMENDATION_TYPE_TRANSACTION_ALERTS = "transaction_alerts"
RECOMMENDATION_RATIONALE_TRANSACTION_ALERTS = (
    "This dispute involved an unrecognized charge. Enabling instant transaction "
    "alerts can help you spot similar charges sooner."
)


class SupportCaseService:
    def __init__(self, session_factory: SessionFactory = create_session) -> None:
        self._session_factory = session_factory

    def open_transaction_dispute(
        self,
        transaction_id: str,
        customer_id: str,
        reason: str,
    ) -> DisputeCase:
        logger.info(
            "open_transaction_dispute called with transaction_id=%s, customer_id=%s",
            transaction_id,
            customer_id,
        )
        _require_identifier(reason, "reason")
        with self._session_factory() as session:
            transaction = _get_owned_transaction(session, transaction_id, customer_id)
            product = _get_active_product(session, transaction.product_id, customer_id)
            _ensure_disputable_status(transaction)
            _ensure_no_active_case(session, transaction_id)
            _ensure_within_dispute_window(transaction.transaction_date)

            case = SupportCase(
                customer_id=customer_id,
                product_id=product.product_id,
                transaction_id=transaction.transaction_id,
                reason=reason.strip(),
                status="WAITING_USER_APPROVAL",
                fraud_score_at_open=transaction.fraud_score,
            )
            session.add(case)
            session.flush()
            _add_event(
                session,
                case.case_id,
                "CASE_OPENED",
                "customer",
                f"Dispute opened for transaction {transaction_id}",
            )
            _add_event(
                session,
                case.case_id,
                "APPROVAL_REQUESTED",
                "system",
                "Customer confirmation required to proceed with the dispute and card block",
            )
            session.commit()
            session.refresh(case)
            return _to_dispute_case(case, product)

    def respond_to_approval(
        self,
        case_id: str,
        customer_id: str,
        approved: bool,
    ) -> DisputeCase:
        logger.info(
            "respond_to_approval called with case_id=%s, approved=%s", case_id, approved
        )
        with self._session_factory() as session:
            case = _get_owned_case(session, case_id, customer_id)
            if case.status != "WAITING_USER_APPROVAL":
                raise ValueError(f"Case {case_id} is not awaiting approval")

            case = _decline_approval(session, case) if not approved else _grant_approval(session, case)
            return _to_dispute_case(case, _get_case_product(session, case))

    def resolve_case(
        self,
        case_id: str,
        customer_id: str,
        resolution_outcome: str,
        resolution_notes: str | None = None,
    ) -> DisputeCase:
        logger.info("resolve_case called with case_id=%s", case_id)
        _require_identifier(resolution_outcome, "resolution_outcome")
        with self._session_factory() as session:
            case = _get_owned_case(session, case_id, customer_id)
            if case.status != "IN_REVIEW":
                raise ValueError(f"Case {case_id} is not in review")
            _transition(case, "RESOLVED", resolution_outcome=resolution_outcome, resolution_notes=resolution_notes)
            _apply_recommendation(case)
            _add_event(
                session,
                case.case_id,
                "RESOLVED",
                "agent",
                resolution_notes or f"Case resolved: {resolution_outcome}",
            )
            session.add(case)
            session.commit()
            session.refresh(case)
            return _to_dispute_case(case, _get_case_product(session, case))

    def list_cases(self, customer_id: str) -> list[DisputeCase]:
        with self._session_factory() as session:
            statement = (
                select(SupportCase)
                .where(SupportCase.customer_id == customer_id)
                .order_by(SupportCase.opened_at.desc())
            )
            return [
                _to_dispute_case(case, _get_case_product(session, case))
                for case in session.exec(statement).all()
            ]

    def get_case(self, case_id: str, customer_id: str) -> DisputeCase:
        with self._session_factory() as session:
            case = _get_owned_case(session, case_id, customer_id)
            return _to_dispute_case(case, _get_case_product(session, case))

    def get_case_timeline(self, case_id: str, customer_id: str) -> list[DisputeCaseEvent]:
        with self._session_factory() as session:
            _get_owned_case(session, case_id, customer_id)
            statement = (
                select(SupportCaseEvent)
                .where(SupportCaseEvent.case_id == case_id)
                .order_by(SupportCaseEvent.created_at.asc())
            )
            return [_to_dispute_case_event(event) for event in session.exec(statement).all()]

    def dismiss_recommendation(self, case_id: str, customer_id: str) -> DisputeCase:
        logger.info("dismiss_recommendation called with case_id=%s", case_id)
        with self._session_factory() as session:
            case = _get_owned_case(session, case_id, customer_id)
            if case.recommendation_type is None:
                raise ValueError(f"Case {case_id} has no recommendation to dismiss")
            case.recommendation_opted_out = True
            case.updated_at = datetime.now(timezone.utc)
            session.add(case)
            _add_event(
                session,
                case.case_id,
                "RECOMMENDATION_DISMISSED",
                "customer",
                "Customer dismissed the post-resolution recommendation",
            )
            session.commit()
            session.refresh(case)
            return _to_dispute_case(case, _get_case_product(session, case))


support_case_service_singleton = SupportCaseService()


def _decline_approval(session: Session, case: SupportCase) -> SupportCase:
    _transition(case, "RESOLVED", resolution_outcome="withdrawn_by_customer")
    _add_event(
        session,
        case.case_id,
        "APPROVAL_DECLINED",
        "customer",
        "Customer declined to proceed with the dispute",
    )
    _add_event(session, case.case_id, "RESOLVED", "system", "Case closed: withdrawn by customer")
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def _grant_approval(session: Session, case: SupportCase) -> SupportCase:
    triage_outcome = _triage(case.fraud_score_at_open)
    case.triage_outcome = triage_outcome
    _transition(case, "IN_REVIEW")
    _add_event(
        session,
        case.case_id,
        "APPROVAL_GRANTED",
        "customer",
        "Customer approved the dispute and card block",
    )

    if triage_outcome == TRIAGE_FAST_TRACK:
        _add_event(
            session,
            case.case_id,
            "FAST_TRACKED",
            "system",
            "Low fraud-risk score; fast-tracked without manual review",
        )
        _transition(case, "RESOLVED", resolution_outcome="fast_tracked_provisional_credit")
        _apply_recommendation(case)
        _add_event(
            session,
            case.case_id,
            "RESOLVED",
            "system",
            "Provisional credit issued; case resolved without manual review",
        )
    else:
        agent = _assign_review_agent(session)
        case.assigned_agent_id = agent.agent_id if agent else None
        reason = (
            "Elevated fraud-risk score"
            if triage_outcome == TRIAGE_ESCALATED
            else "No fraud score available for this transaction"
        )
        agent_note = f" (assigned to agent {agent.agent_id})" if agent else " (no agent available)"
        _add_event(
            session,
            case.case_id,
            "ESCALATED_TO_REVIEW",
            "system",
            f"{reason}; routed to manual review{agent_note}",
        )

    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def _require_identifier(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} is empty or null")


def _get_owned_transaction(
    session: Session, transaction_id: str, customer_id: str
) -> TransactionRecord:
    _require_identifier(transaction_id, "transaction_id")
    statement = (
        select(TransactionRecord)
        .where(TransactionRecord.transaction_id == transaction_id)
        .where(TransactionRecord.customer_id == customer_id)
    )
    transaction = session.exec(statement).first()
    if transaction is None:
        raise PermissionError("Transaction does not belong to the authenticated customer")
    return transaction


def _get_active_product(session: Session, product_id: str, customer_id: str) -> Product:
    statement = (
        select(Product)
        .where(Product.product_id == product_id)
        .where(Product.customer_id == customer_id)
    )
    product = session.exec(statement).first()
    if product is None:
        raise PermissionError("Product does not belong to the authenticated customer")
    if product.product_status != ACTIVE_PRODUCT_STATUS:
        raise ValueError(
            f"Product must be {ACTIVE_PRODUCT_STATUS} to open a dispute, "
            f"current status: {product.product_status}"
        )
    return product


def _ensure_disputable_status(transaction: TransactionRecord) -> None:
    if transaction.transaction_status != DISPUTABLE_TRANSACTION_STATUS:
        raise ValueError(f"Only {DISPUTABLE_TRANSACTION_STATUS} transactions can be disputed")


def _ensure_no_active_case(session: Session, transaction_id: str) -> None:
    statement = (
        select(SupportCase)
        .where(SupportCase.transaction_id == transaction_id)
        .where(SupportCase.status != "RESOLVED")
    )
    if session.exec(statement).first() is not None:
        raise ValueError("Transaction already has an active dispute case")


def _ensure_within_dispute_window(transaction_date: datetime) -> None:
    if transaction_date.tzinfo is None:
        transaction_date = transaction_date.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=DISPUTE_WINDOW_DAYS)
    if transaction_date < cutoff:
        raise ValueError(f"Transaction is outside the {DISPUTE_WINDOW_DAYS}-day dispute window")


def _get_owned_case(session: Session, case_id: str, customer_id: str) -> SupportCase:
    _require_identifier(case_id, "case_id")
    statement = (
        select(SupportCase)
        .where(SupportCase.case_id == case_id)
        .where(SupportCase.customer_id == customer_id)
    )
    case = session.exec(statement).first()
    if case is None:
        raise PermissionError("Case does not belong to the authenticated customer")
    return case


def _transition(
    case: SupportCase,
    new_status: str,
    *,
    resolution_outcome: str | None = None,
    resolution_notes: str | None = None,
) -> None:
    case.status = new_status
    case.updated_at = datetime.now(timezone.utc)
    if new_status == "RESOLVED":
        case.resolved_at = case.updated_at
        if resolution_outcome:
            case.resolution_outcome = resolution_outcome
        if resolution_notes:
            case.resolution_notes = resolution_notes


def _triage(fraud_score: Decimal | None) -> str:
    if fraud_score is None:
        return TRIAGE_INSUFFICIENT_SIGNAL
    if fraud_score >= FRAUD_SCORE_ESCALATION_THRESHOLD:
        return TRIAGE_ESCALATED
    return TRIAGE_FAST_TRACK


def _apply_recommendation(case: SupportCase) -> None:
    """Set the single post-resolution recommendation, only for a favorable outcome."""
    if case.resolution_outcome not in FAVORABLE_RESOLUTION_OUTCOMES:
        return
    case.recommendation_type = RECOMMENDATION_TYPE_TRANSACTION_ALERTS
    case.recommendation_rationale = RECOMMENDATION_RATIONALE_TRANSACTION_ALERTS


def _assign_review_agent(session: Session) -> ServiceAgent | None:
    statement = (
        select(ServiceAgent)
        .where(ServiceAgent.agent_status == REVIEW_AGENT_STATUS)
        .where(ServiceAgent.specialty == REVIEW_AGENT_SPECIALTY)
        .order_by(ServiceAgent.agent_id)
        .limit(1)
    )
    return session.exec(statement).first()


def _add_event(
    session: Session,
    case_id: str,
    event_type: str,
    actor: str,
    message: str | None,
) -> None:
    session.add(
        SupportCaseEvent(
            case_id=case_id,
            event_type=event_type,
            actor=actor,
            message=message,
        )
    )


def _get_case_product(session: Session, case: SupportCase) -> Product | None:
    return session.get(Product, case.product_id)


def _product_display_number(product: Product | None) -> str | None:
    if product is None:
        return None
    product_number = product.product_number
    if product.product_type in CARD_PRODUCT_TYPES and product_number and len(product_number) > 4:
        return f"**** {product_number[-4:]}"
    return product_number


def _to_dispute_case(case: SupportCase, product: Product | None) -> DisputeCase:
    return DisputeCase(
        caseId=case.case_id,
        productNumber=_product_display_number(product),
        transactionId=case.transaction_id,
        reason=case.reason,
        status=case.status,
        triageOutcome=case.triage_outcome,
        resolutionOutcome=case.resolution_outcome,
        resolutionNotes=case.resolution_notes,
        recommendationType=case.recommendation_type,
        recommendationRationale=case.recommendation_rationale,
        recommendationOptedOut=case.recommendation_opted_out,
        openedAt=case.opened_at.isoformat(),
        updatedAt=case.updated_at.isoformat(),
        resolvedAt=case.resolved_at.isoformat() if case.resolved_at else None,
    )


def _to_dispute_case_event(event: SupportCaseEvent) -> DisputeCaseEvent:
    return DisputeCaseEvent(
        eventType=event.event_type,
        actor=event.actor,
        message=event.message,
        createdAt=event.created_at.isoformat(),
    )
