"""Customer-consented review queue and atomic real-operator takeover."""
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal

from banking_shared.database import create_session
from banking_shared.identity_models import Operator
from banking_shared.models import SupportCase, SupportCaseEvent
from sqlalchemy import func, update
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, select

from operator_identity import OperatorPrincipal
from operator_models import OperatorCaseDetail, OperatorCaseEvent, OperatorCasePage, OperatorCaseSummary


class OperatorPersistenceUnavailable(RuntimeError):
    """Introspected identity does not have a corresponding persisted Operator."""


class OperatorClaimConflict(ValueError):
    """The case is not eligible for an exclusive takeover."""


def _eligible() -> tuple[ColumnElement[bool], ...]:
    consent = select(SupportCaseEvent.event_id).where(
        SupportCaseEvent.case_id == SupportCase.case_id,
        SupportCaseEvent.event_type == "APPROVAL_GRANTED",
        SupportCaseEvent.actor == "customer",
    ).exists()
    return (SupportCase.status == "IN_REVIEW", SupportCase.assigned_operator_sub.is_(None), consent)


def _summary(case: SupportCase) -> OperatorCaseSummary:
    return OperatorCaseSummary(
        caseId=case.case_id, status=case.status, openedAt=case.opened_at.isoformat(),
        updatedAt=case.updated_at.isoformat(), triageOutcome=case.triage_outcome,
        claimVersion=case.claim_version,
    )


def _detail(session: Session, case: SupportCase) -> OperatorCaseDetail:
    if case.assigned_operator_sub is None or case.claimed_at is None:
        raise LookupError("Case not found")
    events = session.exec(select(SupportCaseEvent).where(
        SupportCaseEvent.case_id == case.case_id,
    ).order_by(SupportCaseEvent.created_at, SupportCaseEvent.event_id)).all()
    return OperatorCaseDetail(
        **_summary(case).model_dump(), assignedOperatorSub=case.assigned_operator_sub,
        claimedAt=case.claimed_at.isoformat(), reason=case.reason,
        transactionId=case.transaction_id, productId=case.product_id,
        events=[OperatorCaseEvent(
            eventId=event.event_id, eventType=event.event_type, actor=event.actor,
            message=event.message, createdAt=event.created_at.isoformat(),
            operatorSub=event.operator_sub, operatorIdentityVersion=event.operator_identity_version,
            claimVersion=event.claim_version,
        ) for event in events],
    )


class OperatorCaseService:
    def __init__(self, session_factory: Callable[[], Session] = create_session) -> None:
        self._session_factory = session_factory

    def list_cases(self, principal: OperatorPrincipal, offset: int = 0,
                   limit: int = 50, view: Literal["available", "assigned"] = "available") -> OperatorCasePage:
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("Invalid pagination")
        if view not in ("available", "assigned"):
            raise ValueError("Invalid case view")
        filters = (SupportCase.assigned_operator_sub == principal.sub,) if view == "assigned" else _eligible()
        with self._session_factory() as session:
            total = session.exec(select(func.count()).select_from(SupportCase).where(*filters)).one()
            cases = session.exec(select(SupportCase).where(*filters).order_by(
                SupportCase.opened_at, SupportCase.case_id,
            ).offset(offset).limit(limit)).all()
            return OperatorCasePage(items=[_summary(case) for case in cases], total=total,
                                    offset=offset, limit=limit)

    def get_case(self, case_id: str, principal: OperatorPrincipal) -> OperatorCaseDetail:
        with self._session_factory() as session:
            case = session.exec(select(SupportCase).where(
                SupportCase.case_id == case_id,
                SupportCase.assigned_operator_sub == principal.sub,
            )).first()
            if case is None:
                raise LookupError("Case not found")
            return _detail(session, case)

    def claim_case(self, case_id: str, principal: OperatorPrincipal) -> OperatorCaseDetail:
        with self._session_factory() as session:
            if session.get(Operator, principal.sub) is None:
                raise OperatorPersistenceUnavailable("Persisted operator is unavailable")
            now = datetime.now(timezone.utc)
            # The eligibility predicate is part of the write, so PostgreSQL rechecks it
            # after waiting for a competing claimant's row lock.
            statement = update(SupportCase).where(
                SupportCase.case_id == case_id, *_eligible(),
            ).values(assigned_operator_sub=principal.sub, claimed_at=now, updated_at=now,
                     claim_version=SupportCase.claim_version + 1).returning(SupportCase.case_id)
            claimed_id = session.execute(statement.execution_options(
                synchronize_session=False,
            )).scalar_one_or_none()
            if claimed_id is None:
                raise OperatorClaimConflict("Case is not available for takeover")
            case = session.get(SupportCase, claimed_id)
            if case is None:
                raise LookupError("Case not found")
            session.add(SupportCaseEvent(
                case_id=case.case_id, event_type="OPERATOR_CLAIMED", actor="operator",
                message="Authenticated operator took exclusive ownership of review; no verdict or financial effect",
                operator_sub=principal.sub, operator_identity_version=principal.identity_version,
                claim_version=case.claim_version, created_at=now,
            ))
            session.flush()
            result = _detail(session, case)
            session.commit()
            return result


operator_case_service = OperatorCaseService()
