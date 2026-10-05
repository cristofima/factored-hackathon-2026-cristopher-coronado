"""Application entry point for the browser-facing Responses BFF."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from bff.routers.auth import router as auth_router
from bff.clients.credentials import create_azure_credential
from bff.identity.responses import AsyncCredential
from bff.routers.responses import router as responses_router
from bff.config.settings import Settings
from bff.config.tracing import configure_tracing
from bff.routers.admin import customer_router, router as admin_router


CredentialFactory = Callable[[Settings], AsyncCredential]


def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    credential_factory: CredentialFactory = create_azure_credential,
    auth_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Create the BFF with application-lifetime upstream resources."""
    app_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = app_settings
        app.state.auth_client = httpx.AsyncClient(
            base_url=app_settings.auth_users_endpoint,
            timeout=3.0, transport=auth_transport, follow_redirects=False,
        )
        app.state.http_client = httpx.AsyncClient(timeout=None, transport=transport)
        HTTPXClientInstrumentor.instrument_client(
            app.state.http_client, tracer_provider=tracer_provider
        )
        app.state.azure_credential = None
        try:
            if app_settings.responses_upstream_mode == "foundry":
                app.state.azure_credential = credential_factory(app_settings)
            yield
        finally:
            await app.state.auth_client.aclose()
            await app.state.http_client.aclose()
            if app.state.azure_credential is not None:
                await app.state.azure_credential.close()

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    tracer_provider = configure_tracing(app, app_settings.applicationinsights_connection_string)
    app.include_router(auth_router, tags=["auth"])
    app.include_router(admin_router, tags=["admin"])
    app.include_router(customer_router, tags=["admin"])
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