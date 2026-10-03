"""W3C context reaches the mounted MCP HTTP boundary."""

from __future__ import annotations

from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from banking_shared.tracing import create_tracer_provider
from main import create_app


def test_mcp_request_preserves_incoming_trace_context() -> None:
    exporter = InMemorySpanExporter()
    provider = create_tracer_provider("banking-assistant-account", None)
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace_id = "1234567890abcdef1234567890abcdef"
    with TestClient(create_app()) as client:
        client.get("/mcp/", headers={
            "traceparent": f"00-{trace_id}-1234567890abcdef-01",
            "tracestate": "bank=opaque",
        })

    spans = [span for span in exporter.get_finished_spans() if span.parent is not None]
    assert spans
    server_span = next(span for span in spans if span.parent.is_remote)
    assert server_span.context.trace_id == int(trace_id, 16)
    assert server_span.context.trace_state.get("bank") == "opaque"
    processor.shutdown()