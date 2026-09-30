"""JWT authentication boundary for browser requests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pydantic import BaseModel, Field, ValidationError
from pwdlib import PasswordHash
from sqlalchemy.exc import SQLAlchemyError

from bff.settings import Settings
from bff.user_repository import UserRepository


class AuthenticatedUser(BaseModel):
    """Identity claims required by the banking assistant."""

    sub: str
    customer_id: str
    email: str
    locale: str


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class UserProfile(AuthenticatedUser):
    name: str | None = None


class AccountSummary(BaseModel):
    type: str
    status: str | None
    opened: date | None
    number: str | None
    currency: str
    balance: str | None


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserProfile


class CardSummary(AccountSummary):
    expires: date | None
    credit_limit: str | None


bearer_scheme = HTTPBearer(auto_error=False)
password_hash = PasswordHash.recommended()
dummy_password_hash = (
    "$argon2id$v=19$m=65536,t=3,p=4$A5X21KRQt4Rd804DVrNBCw$"
    "rKAM3NM6uy3byFjnM8kK2SFM4UGSs1BY/S4f7BrYmMk"
)
router = APIRouter(prefix="/auth")


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request) -> LoginResponse:
    """Verify persisted credentials and issue a short-lived stateless JWT."""
    settings: Settings = request.app.state.settings
    if not settings.jwt_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )

    normalized_email = payload.email.strip().lower()
    user_repository: UserRepository = request.app.state.user_repository
    try:
        configured_user = user_repository.find_by_email(normalized_email)
    except (RuntimeError, SQLAlchemyError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is temporarily unavailable",
        ) from None

    comparison_hash = configured_user.password_hash if configured_user else dummy_password_hash
    if not password_hash.verify(payload.password, comparison_hash) or configured_user is None:
        raise _unauthorized("Invalid email or password")

    user = AuthenticatedUser(
        sub=configured_user.id,
        customer_id=configured_user.customer_id,
        email=configured_user.email,
        locale=configured_user.locale,
    )
    now = datetime.now(timezone.utc)
    expires_in = settings.jwt_access_token_minutes * 60
    token = jwt.encode(
        {
            **user.model_dump(),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )
    return LoginResponse(
        access_token=token, expires_in=expires_in, user=_get_profile(user, request)
    )


@router.get("/me", response_model=UserProfile)
def get_current_user(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
) -> UserProfile:
    """Return the persisted profile for the verified bearer identity."""
    return _get_profile(user, request)


@router.get("/me/accounts", response_model=list[AccountSummary])
def get_current_user_accounts(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
) -> list[AccountSummary]:
    """List only bank accounts owned by the verified identity."""
    repository: UserRepository = request.app.state.user_repository
    try:
        products = repository.list_accounts(user.sub, user.customer_id)
    except (RuntimeError, SQLAlchemyError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Accounts are temporarily unavailable",
        ) from None
    return [AccountSummary(
        type=product.product_type,
        status=product.product_status,
        opened=product.opening_date,
        number=product.product_number,
        currency=product.currency,
        balance=format(product.current_balance, "f") if product.current_balance is not None else None,
    ) for product in products]


@router.get("/me/cards", response_model=list[CardSummary])
def get_current_user_cards(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
) -> list[CardSummary]:
    """List persisted credit and debit cards owned by the verified identity."""
    repository: UserRepository = request.app.state.user_repository
    try:
        products = repository.list_cards(user.sub, user.customer_id)
    except (RuntimeError, SQLAlchemyError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cards are temporarily unavailable",
        ) from None
    return [CardSummary(
        type=product.product_type,
        status=product.product_status,
        opened=product.opening_date,
        expires=product.expiration_date,
        number=(
            f"**** {product.product_number[-4:]}"
            if product.product_number and len(product.product_number) > 4 else None
        ),
        currency=product.currency,
        balance=format(product.current_balance, "f") if product.current_balance is not None else None,
        credit_limit=format(product.credit_limit, "f") if product.credit_limit is not None else None,
    ) for product in products]


def _get_profile(user: AuthenticatedUser, request: Request) -> UserProfile:
    repository: UserRepository = request.app.state.user_repository
    try:
        name = repository.find_customer_name(user.sub, user.customer_id)
    except (RuntimeError, SQLAlchemyError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User profile is temporarily unavailable",
        ) from None
    return UserProfile(**user.model_dump(), name=name)


def get_authenticated_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthenticatedUser:
    """Validate the caller's JWT and return its required identity claims."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Bearer token is required")

    settings: Settings = request.app.state.settings
    if not settings.jwt_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT validation is not configured",
        )

    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "customer_id", "email", "locale"]},
        )
        return AuthenticatedUser.model_validate(claims)
    except (InvalidTokenError, ValidationError):
        raise _unauthorized("Invalid or expired bearer token") from None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )