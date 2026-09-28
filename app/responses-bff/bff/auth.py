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

from bff.settings import Settings


class AuthenticatedUser(BaseModel):
    """Identity claims required by the banking assistant."""

    sub: str
    customer_id: str
    email: str
    locale: str


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: AuthenticatedUser


bearer_scheme = HTTPBearer(auto_error=False)
password_hash = PasswordHash.recommended()
router = APIRouter(prefix="/auth")


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request) -> LoginResponse:
    """Verify configured credentials and issue a short-lived stateless JWT."""
    settings: Settings = request.app.state.settings
    if not settings.jwt_secret_key or not settings.auth_users:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )

    normalized_email = payload.email.strip().lower()
    configured_user = next(
        (user for user in settings.auth_users if user.email.strip().lower() == normalized_email),
        None,
    )
    comparison_hash = configured_user.password_hash if configured_user else settings.auth_users[0].password_hash
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
    return LoginResponse(access_token=token, expires_in=expires_in, user=user)


@router.get("/me", response_model=AuthenticatedUser)
def get_current_user(
    user: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
) -> AuthenticatedUser:
    """Return claims only after the bearer token passes full validation."""
    return user


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