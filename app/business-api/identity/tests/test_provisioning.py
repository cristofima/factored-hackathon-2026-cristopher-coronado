from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from banking_shared import Customer, CustomerUser, User
from banking_shared.identity_models import IdentityAudit
from identity.services.provisioning import seed_users, validate_password


def test_provisioning_refresh_owns_profile_audit_and_single_commit(engine: Engine) -> None:
    commits: list[str] = []

    class RecordingSession(Session):
        def commit(self) -> None:
            commits.append("commit")
            super().commit()

    @contextmanager
    def sessions() -> Iterator[Session]:
        with RecordingSession(engine) as session:
            yield session

    with Session(engine) as session:
        customer = session.get(Customer, "synthetic-customer")
        assert customer is not None
        customer.first_name = "  Test  "
        customer.last_name = " Customer "
        session.add(customer)
        session.commit()

    result = seed_users(
        ("synthetic-customer", "missing"), "en", "synthetic-replacement",
        session_factory=sessions,
    )

    assert commits == ["commit"]
    assert result.seeded_customer_ids == ("synthetic-customer",)
    assert result.skipped_customer_ids == ("missing",)
    with Session(engine) as session:
        user = session.get(User, "customer")
        assert user is not None
        assert (user.name, user.locale, user.status, user.identity_version) == (
            "Test Customer", "en", "active", 2,
        )
        assert session.get(CustomerUser, user.id).customer_id == "synthetic-customer"
        audits = session.exec(select(IdentityAudit)).all()
        assert [(audit.target_id, audit.action) for audit in audits] == [
            ("customer", "customer_migrate"),
        ]


@pytest.mark.parametrize("password,admin", [(" ", None), ("synthetic", "synthetic")])
def test_invalid_credentials_fail_before_opening_session(
    password: str, admin: str | None,
) -> None:
    def forbidden_session() -> Session:
        pytest.fail("Credential validation must precede database access")

    with pytest.raises(ValueError):
        seed_users((), None, password, session_factory=forbidden_session,
                   administrator_password=admin)


def test_administrator_password_comparison_preserves_exact_value() -> None:
    validate_password("synthetic", " synthetic ")
