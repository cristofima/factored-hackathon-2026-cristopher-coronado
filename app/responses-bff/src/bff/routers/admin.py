"""Explicitly allowlisted admin facade; identity service owns mutations."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, field_validator

from bff.identity.models import LoginRequest, UserProfile
from bff.identity.authentication import bearer_scheme, get_authenticated_user
from bff.clients.identity import auth_request

router = APIRouter(prefix="/admin/operators")
customer_router = APIRouter(prefix="/admin/customers")


class CreateOperatorRequest(LoginRequest):
    password: str = Field(min_length=12, max_length=256)
    locale: Literal["en", "es", "pt"]
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def trim_name(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=12, max_length=256)


async def require_admin(
    user: Annotated[UserProfile, Depends(get_authenticated_user)],
) -> UserProfile:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail={"code": "ACCESS_DENIED"})
    return user


async def forward(
    request: Request, credentials: HTTPAuthorizationCredentials,
    method: str, path: str, payload: dict[str, Any] | None = None,
) -> Any:
    return await auth_request(request.app.state.auth_client, method, path,
                              token=credentials.credentials, payload=payload, preserve_status=True)


@customer_router.get("")
async def list_customers(
    request: Request, admin: Annotated[UserProfile, Depends(require_admin)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Any:
    return await forward(request, credentials, "GET", "/admin/customers")


@customer_router.post("/{user_id}/activate")
async def activate_customer(
    user_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=128)], request: Request,
    admin: Annotated[UserProfile, Depends(require_admin)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Any:
    return await forward(request, credentials, "POST", f"/admin/customers/{user_id}/activate")


@customer_router.post("/{user_id}/deactivate")
async def deactivate_customer(
    user_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=128)], request: Request,
    admin: Annotated[UserProfile, Depends(require_admin)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Any:
    return await forward(request, credentials, "POST", f"/admin/customers/{user_id}/deactivate")


@router.get("")
async def list_operators(
    request: Request, admin: Annotated[UserProfile, Depends(require_admin)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Any:
    return await forward(request, credentials, "GET", "/admin/operators")


@router.post("")
async def create_operator(
    payload: CreateOperatorRequest, request: Request,
    admin: Annotated[UserProfile, Depends(require_admin)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Any:
    return await forward(request, credentials, "POST", "/admin/operators",
                         payload.model_dump(exclude_none=True))


@router.post("/{user_id}/activate")
async def activate_operator(
    user_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=128)], request: Request,
    admin: Annotated[UserProfile, Depends(require_admin)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Any:
    return await forward(request, credentials, "POST", f"/admin/operators/{user_id}/activate")


@router.post("/{user_id}/deactivate")
async def deactivate_operator(
    user_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=128)], request: Request,
    admin: Annotated[UserProfile, Depends(require_admin)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Any:
    return await forward(request, credentials, "POST", f"/admin/operators/{user_id}/deactivate")


@router.post("/{user_id}/reset-password")
async def reset_operator_password(
    user_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=128)], payload: ResetPasswordRequest, request: Request,
    admin: Annotated[UserProfile, Depends(require_admin)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Any:
    return await forward(request, credentials, "POST", f"/admin/operators/{user_id}/reset-password",
                         payload.model_dump())
