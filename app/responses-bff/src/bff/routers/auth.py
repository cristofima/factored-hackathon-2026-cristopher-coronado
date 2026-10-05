"""Allowlisted Identity login and profile HTTP facade."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError

from bff.clients.identity import auth_request, unavailable
from bff.identity.authentication import (
    _unauthorized, bearer_scheme, decode_identity, get_authenticated_user,
)
from bff.identity.models import AuthenticatedUser, LoginRequest, LoginResponse, UserProfile

router = APIRouter(prefix="/auth")


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
