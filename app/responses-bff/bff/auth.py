"""Application JWT verification and identity-service auth facade."""

from __future__ import annotations

from typing import Annotated, Any, Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from bff.auth_client import auth_request, unavailable
from bff.settings import Settings


class AuthenticatedUser(BaseModel):
    sub: str = Field(min_length=1)
    email: str = Field(min_length=1)
    locale: str = Field(min_length=1)
    role: Literal["customer", "operator", "admin"]
    identity_version: int = Field(strict=True, ge=1)
    customer_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_role(self) -> AuthenticatedUser:
        if any(not value.strip() for value in (self.sub, self.email, self.locale)):
            raise ValueError("Empty identity")
        if self.customer_id is not None and not self.customer_id.strip():
            raise ValueError("Empty customer identity")
        if (self.role == "customer") != (self.customer_id is not None):
            raise ValueError("Invalid role association")
        return self


class UserProfile(AuthenticatedUser):
    name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_staff_customer_field(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("role") in ("operator", "admin") and "customer_id" in data:
            raise ValueError("Staff profile must omit customer identity")
        return data


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
    user: UserProfile


bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/auth")


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


@router.post("/login", response_model=LoginResponse, response_model_exclude_none=True)
async def login(payload: LoginRequest, request: Request) -> LoginResponse:
    data = await auth_request(request.app.state.auth_client, "POST", "/auth/login",
                              payload=payload.model_dump())
    try:
        result = LoginResponse.model_validate(data)
        identity = decode_identity(result.access_token, request.app.state.settings)
        if result.user.model_dump(include=set(AuthenticatedUser.model_fields)) != identity.model_dump():
            raise unavailable()
        return result
    except (ValidationError, HTTPException):
        raise unavailable() from None


@router.get("/me", response_model=UserProfile, response_model_exclude_none=True)
async def get_current_user(
    request: Request,
    user: Annotated[UserProfile, Depends(get_authenticated_user)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> UserProfile:
    data = await auth_request(request.app.state.auth_client, "GET", "/auth/me",
                              token=credentials.credentials)
    try:
        profile = UserProfile.model_validate(data)
    except ValidationError:
        raise unavailable() from None
    identity_fields = set(AuthenticatedUser.model_fields)
    if profile.model_dump(include=identity_fields) != user.model_dump(include=identity_fields):
        raise _unauthorized()
    return profile
