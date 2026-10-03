"""Auth HTTP boundary. Synchronous handlers run database/hash work in worker threads."""
from collections.abc import Iterator
from contextlib import asynccontextmanager
from hmac import compare_digest
from typing import Annotated, AsyncIterator

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, create_engine
from starlette.concurrency import run_in_threadpool

from identity.schemas import (
    CustomerProfile, IntrospectionRequest, LoginRequest, LoginResponse,
    OperatorCreate, PasswordReset, UserProfile,
)
from identity.service import IdentityService, unauthorized
from identity.settings import Settings

bearer = HTTPBearer(auto_error=False)


def token_value(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    return credentials.credentials


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    config = settings or Settings()
    owned_engine = engine is None
    database = engine if engine is not None else create_engine(
        config.database_url.get_secret_value(), pool_pre_ping=True,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
    )
    service = IdentityService(config)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        yield
        if owned_engine:
            await run_in_threadpool(database.dispose)

    app = FastAPI(title="Banking Identity", lifespan=lifespan)

    def session() -> Iterator[Session]:
        with Session(database) as current:
            yield current

    @app.exception_handler(IntegrityError)
    async def conflict(request: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": {"code": "AUTH_CONFLICT"}})

    @app.exception_handler(SQLAlchemyError)
    async def unavailable(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": {"code": "AUTH_UNAVAILABLE"}})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": {"code": "AUTH_INVALID_REQUEST"}})

    @app.post("/auth/login", response_model=LoginResponse, response_model_exclude_none=True)
    def login(body: LoginRequest, db: Annotated[Session, Depends(session)]) -> LoginResponse:
        return service.login(db, body.email, body.password.get_secret_value())

    @app.get("/auth/me", response_model=CustomerProfile | UserProfile,
             response_model_exclude_none=True)
    def me(db: Annotated[Session, Depends(session)],
           token: Annotated[str, Depends(token_value)]) -> UserProfile:
        return service.profile(db, service.authenticate(db, token))

    def internal(token: Annotated[str, Depends(token_value)]) -> None:
        if not compare_digest(token.encode(), config.auth_internal_secret.get_secret_value().encode()):
            raise unauthorized()

    @app.post("/internal/introspect", response_model=CustomerProfile | UserProfile,
              response_model_exclude_none=True, dependencies=[Depends(internal)])
    def introspect(body: IntrospectionRequest,
                   db: Annotated[Session, Depends(session)]) -> UserProfile:
        return service.profile(db, service.authenticate(db, body.token.get_secret_value()))

    @app.get("/admin/operators", response_model=list[UserProfile], response_model_exclude_none=True)
    def operators(db: Annotated[Session, Depends(session)],
                  token: Annotated[str, Depends(token_value)]) -> list[UserProfile]:
        return service.list_operators(db, token)

    @app.post("/admin/operators", response_model=UserProfile,
              response_model_exclude_none=True, status_code=201)
    def create_operator(body: OperatorCreate, db: Annotated[Session, Depends(session)],
                        token: Annotated[str, Depends(token_value)]) -> UserProfile:
        return service.create_operator(db, token, body)

    @app.post("/admin/operators/{user_id}/activate", response_model=UserProfile,
              response_model_exclude_none=True)
    def activate(user_id: str, db: Annotated[Session, Depends(session)],
                 token: Annotated[str, Depends(token_value)]) -> UserProfile:
        return service.update_operator(db, token, user_id, "activate")

    @app.post("/admin/operators/{user_id}/deactivate", response_model=UserProfile,
              response_model_exclude_none=True)
    def deactivate(user_id: str, db: Annotated[Session, Depends(session)],
                   token: Annotated[str, Depends(token_value)]) -> UserProfile:
        return service.update_operator(db, token, user_id, "deactivate")

    @app.post("/admin/operators/{user_id}/reset-password", response_model=UserProfile,
              response_model_exclude_none=True)
    def reset(user_id: str, body: PasswordReset, db: Annotated[Session, Depends(session)],
              token: Annotated[str, Depends(token_value)]) -> UserProfile:
        return service.update_operator(db, token, user_id, "reset_password",
                                       body.password.get_secret_value())

    @app.get("/admin/customers", response_model=list[CustomerProfile],
             response_model_exclude_none=True)
    def customers(db: Annotated[Session, Depends(session)],
                  token: Annotated[str, Depends(token_value)]) -> list[CustomerProfile]:
        return service.list_customers(db, token)

    @app.post("/admin/customers/{user_id}/activate", response_model=CustomerProfile,
              response_model_exclude_none=True)
    def activate_customer(
        user_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=128)],
        db: Annotated[Session, Depends(session)],
        token: Annotated[str, Depends(token_value)],
    ) -> CustomerProfile:
        return service.update_customer(db, token, user_id, "activate")

    @app.post("/admin/customers/{user_id}/deactivate", response_model=CustomerProfile,
              response_model_exclude_none=True)
    def deactivate_customer(
        user_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=128)],
        db: Annotated[Session, Depends(session)],
        token: Annotated[str, Depends(token_value)],
    ) -> CustomerProfile:
        return service.update_customer(db, token, user_id, "deactivate")

    return app
