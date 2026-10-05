"""JWT validation and uncached current-identity authorization dependencies."""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pydantic import ValidationError

from bff.clients.identity import auth_request, unavailable
from bff.config.settings import Settings
from bff.identity.models import AuthenticatedUser, UserProfile

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(code: str = "AUTH_REQUIRED") -> HTTPException:
    return HTTPException(status_code=401, detail={"code": code},
                         headers={"WWW-Authenticate": "Bearer"})


def decode_identity(token: str, settings: Settings) -> AuthenticatedUser:
    if not settings.jwt_secret_key:
        raise unavailable()
    try:
        claims = jwt.decode(
            token, settings.jwt_secret_key, algorithms=["HS256"],
            audience=settings.jwt_audience, issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "email", "locale", "role", "identity_version"]},
        )
        user = AuthenticatedUser.model_validate(claims)
        if user.role != "customer" and "customer_id" in claims:
            raise _unauthorized()
        return user
    except (InvalidTokenError, ValidationError):
        raise _unauthorized() from None


async def get_authenticated_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> UserProfile:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    settings: Settings = request.app.state.settings
    user = decode_identity(credentials.credentials, settings)
    data = await auth_request(
        request.app.state.auth_client, "POST", "/internal/introspect",
        payload={"token": credentials.credentials}, internal_secret=settings.auth_internal_secret,
    )
    try:
        current = UserProfile.model_validate(data)
    except ValidationError:
        raise unavailable() from None
    if current.model_dump(include=set(AuthenticatedUser.model_fields)) != user.model_dump():
        raise _unauthorized()
    return current


async def get_customer_user(
    user: Annotated[UserProfile, Depends(get_authenticated_user)],
) -> AuthenticatedUser:
    if user.role != "customer":
        raise HTTPException(status_code=403, detail={"code": "ACCESS_DENIED"})
    return user
