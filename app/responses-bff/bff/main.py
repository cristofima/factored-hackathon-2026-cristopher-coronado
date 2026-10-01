"""Application entry point for the browser-facing Responses BFF."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bff.auth import router as auth_router
from bff.credentials import create_azure_credential
from bff.responses import AsyncCredential, router as responses_router
from bff.settings import Settings
from bff.user_repository import SqlModelUserRepository, UserRepository


CredentialFactory = Callable[[Settings], AsyncCredential]


def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    credential_factory: CredentialFactory = create_azure_credential,
    user_repository: UserRepository | None = None,
) -> FastAPI:
    """Create the BFF with application-lifetime upstream resources."""
    app_settings = settings or Settings()
    app_user_repository = user_repository or SqlModelUserRepository()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = app_settings
        app.state.user_repository = app_user_repository
        app.state.http_client = httpx.AsyncClient(timeout=None, transport=transport)
        app.state.azure_credential = (
            credential_factory(app_settings)
            if app_settings.responses_upstream_mode == "foundry"
            else None
        )
        try:
            yield
        finally:
            await app.state.http_client.aclose()
            if app.state.azure_credential is not None:
                await app.state.azure_credential.close()

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.include_router(auth_router, tags=["auth"])
    app.include_router(responses_router, tags=["responses"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Conversation-Id"],
    )
    return app


app = create_app()