"""W3C trace-context propagation for the Responses BFF.

The browser never emits traceparent/tracestate, so the BFF originates the trace:
FastAPI instrumentation creates a root span per incoming request, and httpx
instrumentation injects the resulting traceparent/tracestate into the outbound
call to the agent. Exporting to Azure Monitor is optional and only enabled when
APPLICATIONINSIGHTS_CONNECTION_STRING is set; propagation itself does not
depend on an exporter being configured.
"""

from __future__ import annotations

from banking_shared.tracing import create_meter_provider, create_tracer_provider
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider


def configure_tracing(app: FastAPI, connection_string: str | None) -> TracerProvider:
    """Instrument the inbound boundary without replacing the global provider."""
    provider = create_tracer_provider("banking-assistant-responses-bff", connection_string)
    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=provider,
        meter_provider=create_meter_provider("banking-assistant-responses-bff", connection_string),
    )
    return provider
