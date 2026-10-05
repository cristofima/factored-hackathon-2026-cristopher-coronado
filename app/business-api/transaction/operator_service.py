"""Customer-consented takeover, assigned adjudication and atomic financial effects."""
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal

from banking_shared.database import create_session
from banking_shared.identity_models import Operator
from banking_shared.models import CardProtection, Product, SupportCase, SupportCaseEvent
from adjudication import AdjudicationConflict, advance, audit, capture_evidence, destinations, execute_effects, owned_case, source_snapshot
from sqlalchemy import func, update
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, select

from case_projections import effects as _effects, protection as _protection, product_protection_status
from operator_identity import OperatorPrincipal
from operator_models import AdjudicateRequest, CardProtectionRequest, OperatorCaseDetail, OperatorCaseEvent, OperatorCasePage, OperatorCaseSummary


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
        caseVersion=case.case_version, evidenceVersion=case.evidence_version,
        evidence=case.evidence_snapshot, verdict=case.verdict, rationale=case.resolution_notes,
        eligibleDestinations=[{"productId": product.product_id, "productNumber": (f"**** {product.product_number[-4:]}" if product.product_type == "Credit Card" and product.product_number else product.product_number),
                               "productType": product.product_type, "currency": product.currency} for product in destinations(session, case)],
        effectCode=case.effect_code, effects=_effects(session, case), cardProtection=_protection(session, case),
        productProtectionStatus=product_protection_status(session, case),
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
                     claim_version=SupportCase.claim_version + 1, case_version=SupportCase.case_version + 1).returning(SupportCase.case_id)
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
            if session.get(Product, case.product_id) is not None:
                capture_evidence(session, case)
            session.flush()
            result = _detail(session, case)
            session.commit()
            return result


    def adjudicate(self, case_id: str, principal: OperatorPrincipal, request: AdjudicateRequest) -> OperatorCaseDetail:
        with self._session_factory() as session:
            case = owned_case(session, case_id, principal, request.expected_case_version)
            if case.status != "IN_REVIEW" or case.verdict is not None:
                raise AdjudicationConflict("CASE_VERDICT_CONFLICT")
            if case.evidence_version != request.expected_evidence_version:
                raise AdjudicationConflict("EVIDENCE_VERSION_CONFLICT")
            if case.evidence_snapshot != source_snapshot(session, case):
                case.evidence_snapshot = source_snapshot(session, case)
                case.evidence_version += 1
                advance(case)
                session.add(case)
                session.commit()
                raise AdjudicationConflict("EVIDENCE_VERSION_CONFLICT")
            case.verdict = request.verdict
            case.resolution_notes = request.rationale
            case.status = "PENDING_EFFECTS" if request.verdict == "valid" else "RESOLVED_INVALID"
            if request.verdict == "invalid":
                case.resolved_at = datetime.now(timezone.utc)
                case.resolution_outcome = "dispute_rejected"
            advance(case)
            audit(session, case, principal, "OPERATOR_VERDICT", f"Operator verdict: {request.verdict}. Rationale: {request.rationale}")
            session.add(case)
            session.commit()
            version = case.case_version
        if request.verdict == "valid":
            return self.retry_effects(case_id, principal, version, request.destination_product_id)
        return self.get_case(case_id, principal)

    def retry_effects(self, case_id: str, principal: OperatorPrincipal, version: int,
                      destination_id: str | None = None) -> OperatorCaseDetail:
        from sqlalchemy.exc import SQLAlchemyError
        try:
            with self._session_factory() as session:
                case = owned_case(session, case_id, principal, version)
                execute_effects(session, case, principal, destination_id)
                if case.status == "PENDING_EFFECTS":
                    advance(case)
                    session.add(case)
                session.commit()
        except SQLAlchemyError:
            # The verdict was already durably committed; every attempted effect rolls back together.
            with self._session_factory() as session:
                try:
                    case = owned_case(session, case_id, principal, version)
                except AdjudicationConflict as error:
                    if error.code != "CASE_VERSION_CONFLICT":
                        raise
                    return self.get_case(case_id, principal)
                case.effect_code = "EFFECT_EXECUTION_FAILED"
                advance(case)
                session.add(case)
                session.commit()
        return self.get_case(case_id, principal)

    def protect_card(self, case_id: str, principal: OperatorPrincipal, request: CardProtectionRequest) -> OperatorCaseDetail:
        with self._session_factory() as session:
            case = owned_case(session, case_id, principal, request.expected_case_version)
            product = session.exec(select(Product).where(Product.product_id == case.product_id,
                Product.customer_id == case.customer_id).with_for_update()).first()
            if product is None or product.product_type not in ("Debit Card", "Credit Card"):
                raise AdjudicationConflict("CARD_PROTECTION_NOT_ELIGIBLE")
            protection = session.get(CardProtection, product.product_id)
            if protection is None:
                protection = CardProtection(product_id=product.product_id, case_id=case.case_id,
                    prior_status=product.product_status, blocked=request.blocked, rationale=request.rationale,
                    operator_sub=principal.sub, updated_at=datetime.now(timezone.utc))
            else:
                protection.blocked = request.blocked
                protection.case_id = case.case_id
                protection.rationale = request.rationale
                protection.operator_sub = principal.sub
                protection.updated_at = datetime.now(timezone.utc)
            session.add(protection)
            advance(case)
            session.add(case)
            audit(session, case, principal, "CARD_PROTECTION_CHANGED",
                f"Local card protection blocked={request.blocked}; prior source status={protection.prior_status}. Rationale: {request.rationale}. No external processor enforcement")
            session.commit()
        return self.get_case(case_id, principal)


operator_case_service = OperatorCaseService()
