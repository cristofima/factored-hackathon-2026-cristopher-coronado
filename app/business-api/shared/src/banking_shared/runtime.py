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


def project_runtime_many(
    session: Session, products: list[Product], *, balances: bool = True,
) -> list[Product]:
    """Project runtime state in two bounded reads, or one for status-only callers."""
    if not products:
        return []
    identifiers = {product.product_id for product in products}
    deltas = {}
    if balances:
        rows = session.exec(
            select(RuntimePosting.product_id, func.sum(RuntimePosting.balance_delta))
            .where(RuntimePosting.product_id.in_(identifiers))
            .group_by(RuntimePosting.product_id)
        ).all()
        deltas = {identifier: Decimal(delta) for identifier, delta in rows}
    blocked = {
        protection.product_id
        for protection in session.exec(
            select(CardProtection).where(CardProtection.product_id.in_(identifiers))
        ).all()
        if protection.blocked
    }
    results = []
    for product in products:
        result = Product.model_validate(product.model_dump())
        if balances and result.current_balance is not None:
            result.current_balance += deltas.get(product.product_id, Decimal(0))
        if product.product_id in blocked:
            result.product_status = "Blocked"
        results.append(result)
    return results


def project_runtime(session: Session, product: Product) -> Product:
    return project_runtime_many(session, [product])[0]
