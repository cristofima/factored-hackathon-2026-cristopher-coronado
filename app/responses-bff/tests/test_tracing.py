"""Trace configuration remains independent of Azure export availability."""

from __future__ import annotations

import httpx
import pytest
from azure.monitor.opentelemetry.exporter import (
    AzureMonitorMetricExporter,
    AzureMonitorTraceExporter,
)
from banking_shared.tracing import create_meter_provider, create_tracer_provider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from bff.config.settings import Settings
from bff.main import create_app


def test_meter_provider_is_reused_without_export() -> None:
    provider = create_meter_provider("test-meter-no-export", None)
    assert create_meter_provider("test-meter-no-export", None) is provider
    provider.get_meter(__name__).create_counter("test.counter").add(1)


def test_invalid_metric_export_configuration_preserves_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def invalid_exporter(*args: object, **kwargs: object) -> None:
        raise ValueError("Invalid export configuration")

    monkeypatch.setattr(AzureMonitorMetricExporter, "__init__", invalid_exporter)
    provider = create_meter_provider("test-invalid-metric-export", "invalid")
    provider.get_meter(__name__).create_counter("test.counter").add(1)


def test_metric_export_pipeline_uses_service_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = InMemoryMetricReader()
    configured_exporter = object()

    def create_exporter(*, connection_string: str) -> object:
        assert connection_string == "synthetic-configuration"
        return configured_exporter

    def create_reader(exporter: object) -> InMemoryMetricReader:
        assert exporter is configured_exporter
        return reader

    monkeypatch.setattr(
        "azure.monitor.opentelemetry.exporter.AzureMonitorMetricExporter", create_exporter
    )
    monkeypatch.setattr("banking_shared.tracing.PeriodicExportingMetricReader", create_reader)
    provider = create_meter_provider("test-metric-pipeline", "synthetic-configuration")
    try:
        provider.get_meter(__name__).create_counter("test.counter").add(1)
        data = reader.get_metrics_data()
        assert data is not None
        resource = data.resource_metrics[0]
        assert resource.resource.attributes["service.name"] == "test-metric-pipeline"
        assert resource.scope_metrics[0].metrics[0].data.data_points[0].value == 1
    finally:
        provider.shutdown()


async def test_bff_emits_server_and_both_upstream_client_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[reader])
    exporter = InMemorySpanExporter()
    traces = TracerProvider()
    traces.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr("bff.config.tracing.create_tracer_provider", lambda *args: traces)
    monkeypatch.setattr("bff.config.tracing.create_meter_provider", lambda *args: meters)
    monkeypatch.setattr("bff.main.create_meter_provider", lambda *args: meters)
    contexts: list[str] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        contexts.append(request.headers["traceparent"])
        return httpx.Response(200)

    settings = Settings(_env_file=None, responses_upstream_mode="local")
    app = create_app(
        settings,
        transport=httpx.MockTransport(upstream),
        auth_transport=httpx.MockTransport(upstream),
    )
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://bff"
            ) as client:
                assert (await client.get("/openapi.json")).status_code == 200
            with traces.get_tracer(__name__).start_as_current_span("parent") as parent:
                await app.state.auth_client.get("/auth/me")
                await app.state.http_client.get("http://agent/responses")
                expected_trace = f"{parent.get_span_context().trace_id:032x}"
        assert len(contexts) == 2
        assert all(context.split("-")[1] == expected_trace for context in contexts)
        spans = exporter.get_finished_spans()
        assert sum(span.kind == SpanKind.SERVER for span in spans) == 1
        assert sum(span.kind == SpanKind.CLIENT for span in spans) == 2
        data = reader.get_metrics_data()
        assert data is not None
        metrics = [
            metric
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
        ]
        for names, count in (
            ({"http.server.duration", "http.server.request.duration"}, 1),
            ({"http.client.duration", "http.client.request.duration"}, 2),
        ):
            duration = next(metric for metric in metrics if metric.name in names)
            assert sum(point.count for point in duration.data.data_points) == count
    finally:
        traces.shutdown()
        meters.shutdown()


def test_provider_is_reused_without_export() -> None:
    provider = create_tracer_provider("test-no-export", None)

    assert create_tracer_provider("test-no-export", None) is provider
    assert provider.resource.attributes["service.name"] == "test-no-export"
    with provider.get_tracer(__name__).start_as_current_span("test") as span:
        assert span.get_span_context().is_valid


def test_invalid_export_configuration_does_not_disable_tracing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def invalid_exporter(*args: object, **kwargs: object) -> None:
        raise ValueError("Invalid export configuration")

    monkeypatch.setattr(AzureMonitorTraceExporter, "__init__", invalid_exporter)
    provider = create_tracer_provider("test-invalid-export", "invalid")

    with provider.get_tracer(__name__).start_as_current_span("test") as span:
        assert span.get_span_context().is_valid