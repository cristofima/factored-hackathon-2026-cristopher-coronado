"""Bounded runtime reads preserve persisted financial anchors."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlmodel import Session, create_engine, select

from banking_shared.models import CardProtection, Product, RuntimePosting, SQLModel
from banking_shared.runtime import effective_balance, project_runtime, project_runtime_many


@pytest.mark.parametrize("count", [1, 8])
def test_batch_projection_has_constant_query_budget(count: int) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        products = [
            Product(product_id=f"p-{index}", customer_id="owner", product_type="Credit Card",
                    currency="USD", current_balance=Decimal("100.2500"), product_status="Active")
            for index in range(count)
        ]
        products[-1].current_balance = None
        session.add_all(products)
        session.add_all([
            RuntimePosting(original_transaction_id="original", case_id="case", movement_id="movement",
                           product_id="p-0", customer_id="owner", amount=Decimal("2.1250"),
                           balance_delta=Decimal("-2.1250"), currency="USD", operator_sub="operator",
                           executed_at=now),
            CardProtection(product_id="p-0", case_id="case", rationale="Synthetic protection",
                           operator_sub="operator", updated_at=now),
        ])
        session.commit()
        products = sorted(session.exec(select(Product)).all(), key=lambda product: product.product_id)
        statements: list[str] = []

        def record_query(*args: object) -> None:
            statements.append(str(args[2]))

        event.listen(engine, "before_cursor_execute", record_query)
        assert project_runtime_many(session, []) == []
        assert statements == []
        projected = project_runtime_many(session, products)
        assert len(statements) == 2
        assert projected[0].product_status == "Blocked"
        assert projected[-1].current_balance is None
        if count > 1:
            assert projected[0].current_balance == Decimal("98.1250")
        statements.clear()
        status_only = project_runtime_many(session, products, balances=False)
        assert len(statements) == 1
        assert status_only[0].current_balance == products[0].current_balance
        assert status_only[0].product_status == "Blocked"
        for original, result in zip(products, projected, strict=True):
            assert result.current_balance == effective_balance(session, original)
            assert result.model_dump() == project_runtime(session, original).model_dump()
            assert original.product_status == "Active"
            assert original.current_balance == (None if original is products[-1] else Decimal("100.2500"))
            assert result is not original
        assert not session.dirty
    engine.dispose()
