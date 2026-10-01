"""JWT authentication boundary for browser requests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserProfile


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
            detail={"code": "SERVICE_UNAVAILABLE"},
        )

    normalized_email = payload.email.strip().lower()
    user_repository: UserRepository = request.app.state.user_repository
    try:
        configured_user = user_repository.find_by_email(normalized_email)
    except (RuntimeError, SQLAlchemyError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE"},
        ) from None

    comparison_hash = configured_user.password_hash if configured_user else dummy_password_hash
    if not password_hash.verify(payload.password, comparison_hash) or configured_user is None:
        raise _unauthorized("INVALID_CREDENTIALS")

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


def _get_profile(user: AuthenticatedUser, request: Request) -> UserProfile:
    repository: UserRepository = request.app.state.user_repository
    try:
        name = repository.find_customer_name(user.sub, user.customer_id)
    except (RuntimeError, SQLAlchemyError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE"},
        ) from None
    return UserProfile(**user.model_dump(), name=name)


def get_authenticated_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthenticatedUser:
    """Validate the caller's JWT and return its required identity claims."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("AUTH_REQUIRED")

    settings: Settings = request.app.state.settings
    if not settings.jwt_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE"},
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
        raise _unauthorized("AUTH_REQUIRED") from None


def _unauthorized(code: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code},
        headers={"WWW-Authenticate": "Bearer"},
    )