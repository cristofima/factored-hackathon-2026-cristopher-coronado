from __future__ import annotations

from io import StringIO
from pathlib import Path
import runpy
from unittest.mock import MagicMock, patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest


ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "alembic"


def test_support_migration_moves_existing_tables_and_creates_retained_history() -> None:
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output},
    )
    revision = runpy.run_path(
        str(ALEMBIC_DIR / "versions" / "20261005_0012_case_conversation_history.py"),
    )
    with Operations.context(context):
        revision["upgrade"]()
    sql = output.getvalue()
    assert revision["revision"] == "20261005_0012"
    assert revision["revision"] != "20261004_0012"
    assert revision["down_revision"] == "20261004_0011"
    assert "CREATE SCHEMA support" in sql
    for table in ("support_cases", "support_case_events", "runtime_postings", "card_protections"):
        assert f'ALTER TABLE public."{table}" SET SCHEMA support' in sql
    assert "CREATE TABLE support.case_conversations" in sql
    assert "REFERENCES support.support_cases (case_id) ON DELETE RESTRICT" in sql
    assert "DROP TABLE" not in sql
    with pytest.raises(RuntimeError, match="retention review"):
        revision["downgrade"]()


def test_alembic_reflection_keeps_only_managed_schemas_and_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://offline:offline@localhost/offline")
    config = MagicMock()
    config.config_file_name = None
    with patch("alembic.context.config", config, create=True), \
         patch("alembic.context.is_offline_mode", return_value=True), \
         patch("alembic.context.configure") as configure, \
         patch("alembic.context.begin_transaction"), \
         patch("alembic.context.run_migrations"):
        environment = runpy.run_path(str(ALEMBIC_DIR / "env.py"))
    include_name = environment["include_name"]
    assert configure.call_args.kwargs["include_schemas"] is True
    assert configure.call_args.kwargs["include_name"] is include_name
    for schema, expected in ((None, True), ("support", True), ("unrelated", False)):
        assert include_name(schema, "schema", {}) is expected
    for table, expected in (
        ("products", True), ("support.support_cases", True),
        ("support.case_conversations", True), ("unmanaged_table", False),
        ("support_cases", False), ("unrelated.case_conversations", False),
    ):
        assert include_name(table, "table", {"schema_qualified_table_name": table}) is expected
    assert include_name("any_index", "index", {}) is True
