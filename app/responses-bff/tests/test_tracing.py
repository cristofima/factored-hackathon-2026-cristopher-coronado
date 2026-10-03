"""Trace configuration remains independent of Azure export availability."""

from __future__ import annotations

import pytest
from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
from banking_shared.tracing import create_tracer_provider


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