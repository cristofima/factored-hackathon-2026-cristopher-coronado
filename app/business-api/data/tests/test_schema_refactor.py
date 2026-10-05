"""Offline forward migration and ingestion contract regression checks."""
from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.engine import Connection

from banking_shared.models import (
    CardProtection, CaseConversationSnapshot, Customer, Product, RuntimePosting,
    SQLModel, SupportCase, SupportCaseEvent,
)
from banking_shared.customer_status import normalize_customer_status
from .test_identity_migrations import additive, legacy, revision, run, table


@pytest.mark.parametrize("model", [
    SupportCase, SupportCaseEvent, RuntimePosting, CardProtection, CaseConversationSnapshot,
])
def test_support_models_have_qualified_metadata(model: type[SQLModel]) -> None:
    assert model.__table__.schema == "support"
    assert SQLModel.metadata.tables[f"support.{model.__tablename__}"] is model.__table__


@pytest.mark.parametrize("model,column,target", [
    (SupportCaseEvent, "case_id", "support.support_cases.case_id"),
    (CaseConversationSnapshot, "case_id", "support.support_cases.case_id"),
    (RuntimePosting, "case_id", "support.support_cases.case_id"),
    (CardProtection, "case_id", "support.support_cases.case_id"),
    (SupportCase, "customer_id", "customers.customer_id"),
    (SupportCase, "product_id", "products.product_id"),
    (RuntimePosting, "customer_id", "customers.customer_id"),
    (RuntimePosting, "product_id", "products.product_id"),
    (CardProtection, "product_id", "products.product_id"),
])
def test_support_foreign_keys_preserve_schema_boundaries(
    model: type[SQLModel], column: str, target: str,
) -> None:
    foreign_keys = model.__table__.c[column].foreign_keys
    assert {foreign_key.target_fullname for foreign_key in foreign_keys} == {target}
    target_schema = "support" if target.startswith("support.") else None
    assert {foreign_key.column.table.schema for foreign_key in foreign_keys} == {target_schema}
    assert Customer.__table__.schema is None
    assert Product.__table__.schema is None


@pytest.fixture(autouse=True)
def script_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))


@pytest.fixture
def independent(legacy: Connection, monkeypatch: pytest.MonkeyPatch) -> Connection:
    additive(legacy, monkeypatch)
    run(legacy, revision("20261003_0007_independent_users.py"))
    return legacy


def test_final_schema_preserves_legacy_components(independent: Connection) -> None:
    users = table(independent, "users")
    independent.execute(users.update().values(name="Legacy display", status="inactive",
                                              identity_version=7))
    roles = table(independent, "roles")
    operator_id = independent.execute(sa.select(roles.c.id).where(
        roles.c.name == "operator")).scalar_one()
    assignment = table(independent, "user_roles")
    independent.execute(assignment.update().values(role_id=operator_id))
    independent.execute(table(independent, "operators").insert().values(user_id="principal-1"))
    independent.commit()
    operator = independent.execute(sa.select(table(independent, "operators"))).mappings().one()
    assert operator["first_name"] is None and operator["last_name"] is None
    assert operator["service_agent_id"] is None
    assert "role" not in assignment.c
    assert isinstance(roles.c.id.type, sa.Integer)
    before = dict(independent.execute(sa.select(users)).mappings().one())
    audit_before = list(independent.execute(sa.select(table(independent, "identity_audits"))))
    with pytest.raises(RuntimeError, match="audit history"):
        run(independent, revision("20261003_0007_independent_users.py"), "downgrade")
    assert dict(independent.execute(sa.select(users)).mappings().one()) == before
    assert list(independent.execute(sa.select(table(independent, "identity_audits")))) == audit_before


@pytest.mark.parametrize("name,field,value", [
    ("users", "email", "a" * 121),
    ("customers", "email", "a" * 121), ("customers", "first_name", "a" * 51),
    ("customers", "last_name", "a" * 51), ("customers", "country", "a" * 101),
    ("customers", "customer_status", "active"),
    ("customers", "customer_status", "Unknown"),
])
def test_preflight_rejects_before_any_ddl(
    legacy: Connection, monkeypatch: pytest.MonkeyPatch, name: str, field: str, value: str,
) -> None:
    legacy.execute(table(legacy, name).update().values(**{field: value}))
    legacy.commit()
    ddl: list[str] = []

    def capture(connection: Connection, clause: object, *args: object) -> None:
        if isinstance(clause, sa.schema.DDLElement):
            ddl.append(type(clause).__name__)

    sa.event.listen(legacy, "before_execute", capture)
    try:
        with pytest.raises(RuntimeError, match="preflight"):
            additive(legacy, monkeypatch)
    finally:
        sa.event.remove(legacy, "before_execute", capture)
    assert ddl == []
    assert "roles" not in sa.inspect(legacy).get_table_names()
    assert "status" not in table(legacy, "users").c


def test_fresh_historical_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        paths = sorted((Path(__file__).parents[1] / "alembic" / "versions").glob("*.py"))
        for path in paths:
            module = revision(path.name)
            if module.revision == "20261005_0012":
                break  # The support-schema migration requires PostgreSQL.
            if module.revision == "20261003_0006":
                monkeypatch.setattr(module.context, "get_x_argument", lambda **kwargs: {})
            run(connection, module)
            if module.revision == "20261003_0006":
                assert "id" in table(connection, "roles").c
            if module.revision == "20261003_0007":
                assert "customer_id" not in table(connection, "users").c
        assert "role_id" in table(connection, "user_roles").c
        assert "first_name" in table(connection, "operators").c
        assert "admins" not in sa.inspect(connection).get_table_names()
    engine.dispose()


@pytest.mark.parametrize("source,expected", [(None, None), ("", None), ("  ", None),
    (" active ", "Active"), ("INACTIVE", "Inactive"), (" suspended ", "Suspended"),
    ("closed", "Closed")])
def test_status_normalization(source: str | None, expected: str | None) -> None:
    assert normalize_customer_status(source) == expected


@pytest.mark.parametrize("source,expected", [(" active ", "Active"), ("CLOSED", "Closed"), ("", None)])
def test_customer_mapper_status(source: str, expected: str | None) -> None:
    from banking_data.ingestion.load_scoped_data import map_customer

    row = dict.fromkeys(("first_name", "last_name", "country", "detected_accent", "segment",
                         "registration_date", "registration_branch_id"), "")
    row.update(customer_id="synthetic", email="synthetic@invalid", customer_status=source)
    assert map_customer(row)["customer_status"] == expected


@pytest.mark.parametrize("field,value", [("customer_status", "pending"),
    ("email", "a" * 121), ("first_name", "a" * 51), ("last_name", "a" * 51),
    ("country", "a" * 101)])
def test_customer_mapper_rejects_invalid_values(field: str, value: str) -> None:
    from banking_data.ingestion.load_scoped_data import map_customer

    row = dict.fromkeys(("first_name", "last_name", "country", "detected_accent", "segment",
                         "registration_date", "registration_branch_id", "customer_status"), "")
    row.update(customer_id="synthetic", email="synthetic@invalid")
    row[field] = value
    with pytest.raises(ValueError):
        map_customer(row)


def test_cutover_rollback_preserves_identity_and_allows_retry(
    legacy: Connection, monkeypatch: pytest.MonkeyPatch,
) -> None:
    additive(legacy, monkeypatch)
    before = dict(legacy.execute(sa.select(table(legacy, "users"))).mappings().one())
    assignments = table(legacy, "user_roles")
    legacy.rollback()
    with pytest.raises(RuntimeError, match="cutover validation"):
        with legacy.begin():
            legacy.execute(assignments.delete())
            run(legacy, revision("20261003_0007_independent_users.py"))
    assert legacy.execute(sa.select(assignments)).one().user_id == "principal-1"
    assert dict(legacy.execute(sa.select(table(legacy, "users"))).mappings().one()) == before
    assert "identity_audits" not in sa.inspect(legacy).get_table_names()
    run(legacy, revision("20261003_0007_independent_users.py"))


@pytest.mark.parametrize("migration,direction", [
    ("20261003_0006_identity_associations.py", "downgrade"),
    ("20261003_0007_independent_users.py", "upgrade"),
    ("20261003_0007_independent_users.py", "downgrade"),
])
def test_missing_catalog_rejected_before_ddl(
    legacy: Connection, monkeypatch: pytest.MonkeyPatch, migration: str, direction: str,
) -> None:
    additive(legacy, monkeypatch)
    second = revision(migration)
    if direction == "downgrade" and "0007" in migration:
        run(legacy, second)
        legacy.execute(table(legacy, "identity_audits").delete())
    catalog = table(legacy, "roles")
    legacy.execute(catalog.delete().where(catalog.c.name == "customer"))
    legacy.commit()
    ddl: list[str] = []

    def capture(connection: Connection, clause: object, *args: object) -> None:
        if isinstance(clause, sa.schema.DDLElement):
            ddl.append(type(clause).__name__)

    sa.event.listen(legacy, "before_execute", capture)
    try:
        with pytest.raises(RuntimeError, match="role catalog|missing customer role"):
            run(legacy, second, direction)
    finally:
        sa.event.remove(legacy, "before_execute", capture)
    assert ddl == []


def test_downgrade_preserves_unlinked_operator(
    independent: Connection,
) -> None:
    independent.execute(table(independent, "identity_audits").delete())
    independent.execute(table(independent, "operators").insert().values(
        user_id="principal-1", first_name="Given", last_name="Family"))
    independent.commit()
    with pytest.raises(RuntimeError, match="staff"):
        run(independent, revision("20261003_0007_independent_users.py"), "downgrade")
    assert independent.execute(sa.select(table(independent, "operators").c.first_name)).one() == (
        "Given",)
    assert "customer_id" not in table(independent, "users").c


def test_unknown_status_and_customer_lengths_rejected() -> None:
    with pytest.raises(ValueError):
        normalize_customer_status("pending")
    for field, limit in {"email": 120, "first_name": 50, "last_name": 50, "country": 100}.items():
        values = {"customer_id": "synthetic", "email": "synthetic@invalid", field: "a" * (limit + 1)}
        with pytest.raises(ValidationError):
            Customer.model_validate(values)
    with pytest.raises(ValidationError):
        Customer.model_validate({"customer_id": "synthetic", "email": "synthetic@invalid",
                                 "customer_status": "unknown"})
