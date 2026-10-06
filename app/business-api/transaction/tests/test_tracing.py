"""W3C context reaches the mounted MCP HTTP boundary."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from banking_transaction.main import create_app


def test_mcp_request_preserves_incoming_trace_context(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(
        "banking_transaction.main.create_meter_provider", lambda *args: meter_provider
    )
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    monkeypatch.setattr("banking_transaction.main.create_tracer_provider", lambda *args: provider)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace_id = "1234567890abcdef1234567890abcdef"
    try:
        with TestClient(create_app()) as client:
            client.get(
                "/mcp/",
                headers={
                    "traceparent": f"00-{trace_id}-1234567890abcdef-01",
                    "tracestate": "bank=opaque",
                },
            )
        spans = [span for span in exporter.get_finished_spans() if span.parent is not None]
        assert spans
        server_span = next(span for span in spans if span.parent.is_remote)
        assert server_span.context.trace_id == int(trace_id, 16)
        assert server_span.context.trace_state.get("bank") == "opaque"
        assert server_span.kind == SpanKind.SERVER
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
        provider.shutdown()
        meter_provider.shutdown()