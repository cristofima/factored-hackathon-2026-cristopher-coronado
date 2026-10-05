"""Persisted effect references shared by owned customer and operator case reads."""
from banking_shared.models import CardProtection, Product, RuntimePosting, SupportCase
from sqlmodel import Session, select


def effects(session: Session, case: SupportCase) -> dict[str, str] | None:
    posting = session.exec(select(RuntimePosting).where(RuntimePosting.case_id == case.case_id)).first()
    if posting is None:
        return None
    return {"movementId": posting.movement_id, "destinationProductId": posting.product_id,
            "amount": str(posting.amount), "currency": posting.currency,
            "balanceDelta": str(posting.balance_delta), "executedAt": posting.executed_at.isoformat()}


def protection(session: Session, case: SupportCase) -> dict[str, object] | None:
    record = session.get(CardProtection, case.product_id)
    if record is None:
        return None
    return {"blocked": record.blocked, "priorStatus": record.prior_status,
            "rationale": record.rationale, "caseId": record.case_id,
            "updatedAt": record.updated_at.isoformat(), "scope": "LOCAL_PRODUCT_ONLY"}


def product_protection_status(session: Session, case: SupportCase) -> str | None:
    product = session.exec(select(Product).where(
        Product.product_id == case.product_id, Product.customer_id == case.customer_id,
    )).first()
    if product is None:
        return None
    record = session.get(CardProtection, product.product_id)
    return "Blocked" if record is not None and record.blocked else product.product_status
