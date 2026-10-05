"""Explicit customer identity provisioning; never called by ingestion or startup."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass

from pwdlib import PasswordHash
from sqlmodel import Session, select

from banking_shared.database import create_session
from banking_shared.identity_models import (
    CustomerUser,
    IdentityAudit,
    Operator,
    Role,
    User,
    UserRole,
    utc_now,
)
from banking_shared.models import Customer

password_hasher = PasswordHash.recommended()


@dataclass(frozen=True)
class SeedUsersResult:
    seeded_customer_ids: tuple[str, ...]
    skipped_customer_ids: tuple[str, ...]


def locale_for_customer(customer: Customer, locale_override: str | None) -> str:
    if locale_override:
        return locale_override
    if (customer.country or "").strip().casefold() in {"brazil", "brasil"}:
        return "pt"
    return "es"


def validate_password(password: str, administrator_password: str | None = None) -> None:
    if not password.strip():
        raise ValueError("Demo password must be non-empty")
    if administrator_password is not None and password == administrator_password:
        raise ValueError("Administrator and customer passwords must differ")


def seed_users(
    customer_ids: tuple[str, ...],
    locale: str | None,
    password: str,
    *,
    session_factory: Callable[[], AbstractContextManager[Session]] = create_session,
    administrator_password: str | None = None,
) -> SeedUsersResult:
    validate_password(password, administrator_password)
    with session_factory() as session:
        customers = {
            customer.customer_id: customer
            for customer in session.exec(
                select(Customer).where(Customer.customer_id.in_(customer_ids))
            ).all()
        }
        missing_customer_ids = [
            customer_id for customer_id in customer_ids if customer_id not in customers
        ]
        valid_customer_ids = tuple(
            customer_id for customer_id in customer_ids if customer_id in customers
        )

        if valid_customer_ids:
            if session.exec(select(Role).where(Role.name == "customer")).first() is None:
                raise ValueError("Apply identity migrations before provisioning customers")
            for customer_id in valid_customer_ids:
                _seed_customer(session, customers[customer_id], locale, password)
        session.commit()
        return SeedUsersResult(valid_customer_ids, tuple(missing_customer_ids))


def _seed_customer(
    session: Session, customer: Customer, locale: str | None, password: str
) -> None:
    mapping = session.exec(
        select(CustomerUser).where(CustomerUser.customer_id == customer.customer_id)
    ).first()
    user = None
    if mapping is not None:
        user = session.exec(
            select(User).where(User.id == mapping.user_id).with_for_update()
        ).first()
        assignment = session.get(UserRole, mapping.user_id)
        assigned_role = session.get(Role, assignment.role_id) if assignment is not None else None
        if (
            user is None
            or assigned_role is None
            or assigned_role.name != "customer"
            or session.get(Operator, mapping.user_id) is not None
        ):
            raise ValueError("Invalid customer identity association")
    email = customer.email.strip().lower()
    collision = session.exec(select(User).where(User.email == email)).first()
    if collision is not None and (user is None or collision.id != user.id):
        raise ValueError("Customer email already belongs to another identity")
    name = " ".join(
        component.strip()
        for component in (customer.first_name, customer.last_name)
        if component and component.strip()
    ) or None
    now = utc_now()
    if user is None:
        user = User(
            email=email,
            name=name,
            password_hash=password_hasher.hash(password),
            locale=locale_for_customer(customer, locale),
            status="active",
        )
        session.add(user)
        session.flush()
        session.add(CustomerUser(user_id=user.id, customer_id=customer.customer_id))
        role = session.exec(select(Role).where(Role.name == "customer")).one()
        session.add(UserRole(user_id=user.id, role_id=role.id))
    else:
        user.email = email
        user.name = name
        user.password_hash = password_hasher.hash(password)
        user.locale = locale_for_customer(customer, locale)
        user.status = "active"
        user.identity_version += 1
        user.updated_at = now
        session.add(user)
    session.add(IdentityAudit(target_id=user.id, action="customer_migrate"))
    session.flush()


def build_manifest(
    customer_ids: tuple[str, ...],
    *,
    session_factory: Callable[[], AbstractContextManager[Session]] = create_session,
) -> list[dict[str, str]]:
    with session_factory() as session:
        seeded_users = session.exec(
            select(User, CustomerUser).join(CustomerUser).where(
                CustomerUser.customer_id.in_(customer_ids)
            ).order_by(CustomerUser.customer_id)
        ).all()
        return [
            {
                "user_id": user.id,
                "customer_id": mapping.customer_id,
                "email": user.email,
                "locale": user.locale,
                "status": user.status,
            }
            for user, mapping in seeded_users
        ]
