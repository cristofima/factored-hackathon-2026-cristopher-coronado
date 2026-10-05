"""Source ingestion may not replace generated financial movement IDs."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from banking_shared.models import TransactionRecord
from sqlalchemy.dialects import postgresql

from scripts.load_scoped_data import upsert_batches


def test_source_ingestion_rejects_existing_runtime_id_before_update() -> None:
    session = MagicMock()
    session.get.return_value = TransactionRecord(
        transaction_id="refund", source_kind="runtime",
    )
    with pytest.raises(ValueError, match="cannot overwrite a runtime movement"):
        upsert_batches(session, TransactionRecord, iter([{"transaction_id": "refund"}]), 1)
    session.exec.assert_not_called()


def test_source_upsert_has_database_runtime_collision_guard() -> None:
    session = MagicMock()
    session.get.return_value = None
    assert upsert_batches(session, TransactionRecord, iter([{"transaction_id": "source"}]), 1) == 1
    statement = session.exec.call_args.args[0]
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "WHERE transactions.source_kind =" in compiled
    assert "source" in statement.compile(dialect=postgresql.dialect()).params.values()
