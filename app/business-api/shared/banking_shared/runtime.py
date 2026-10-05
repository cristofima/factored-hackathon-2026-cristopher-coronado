"""Runtime adjustments remain independent of ingestion-owned product anchors."""
from decimal import Decimal

from banking_shared.models import CardProtection, Product, RuntimePosting
from sqlalchemy import func
from sqlmodel import Session, select


def effective_balance(session: Session, product: Product) -> Decimal | None:
    if product.current_balance is None:
        return None
    delta = session.exec(select(func.coalesce(func.sum(RuntimePosting.balance_delta), 0)).where(
        RuntimePosting.product_id == product.product_id,
    )).one()
    return product.current_balance + Decimal(delta)


def project_runtime(session: Session, product: Product) -> Product:
    result = product.model_copy()
    result.current_balance = effective_balance(session, product)
    protection = session.get(CardProtection, product.product_id)
    if protection is not None and protection.blocked:
        result.product_status = "Blocked"
    return result
