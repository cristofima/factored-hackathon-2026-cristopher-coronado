"""Identity emits server telemetry without external exporters."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from sqlalchemy import Engine

from identity.main import create_app
from identity.settings import Settings


def test_identity_emits_server_span_and_request_duration(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    engine: Engine,
) -> None:
    reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[reader])
    exporter = InMemorySpanExporter()
    traces = TracerProvider()
    traces.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr("identity.main.create_tracer_provider", lambda *args: traces)
    monkeypatch.setattr("identity.main.create_meter_provider", lambda *args: meters)
    try:
        with TestClient(create_app(settings, engine)) as client:
            response = client.get(
                "/openapi.json",
                headers={
                    "traceparent": "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01",
                },
            )
        assert response.status_code == 200
        server = next(
            span for span in exporter.get_finished_spans() if span.kind == SpanKind.SERVER
        )
        assert server.context.trace_id == int("1234567890abcdef1234567890abcdef", 16)
        assert server.parent is not None and server.parent.is_remote
        data = reader.get_metrics_data()
        assert data is not None
        metrics = [
            metric
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
        ]
        duration = next(
            metric for metric in metrics
            if metric.name in ("http.server.duration", "http.server.request.duration")
        )
        assert sum(point.count for point in duration.data.data_points) == 1
    finally:
        traces.shutdown()
        meters.shutdown()
