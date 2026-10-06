"""Optional tracing setup shared by the HTTP service boundaries."""

from __future__ import annotations

import logging
from functools import lru_cache

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


@lru_cache(maxsize=None)
def create_tracer_provider(
    service_name: str, connection_string: str | None
) -> TracerProvider:
    """Reuse a provider per service; propagation does not require Azure export."""
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if connection_string:
        try:
            from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter

            provider.add_span_processor(
                BatchSpanProcessor(
                    AzureMonitorTraceExporter(connection_string=connection_string)
                )
            )
        except (ValueError, OSError):
            logging.getLogger(__name__).warning(
                "Azure trace export could not be initialized; propagation remains enabled"
            )
    return provider


@lru_cache(maxsize=None)
def create_meter_provider(
    service_name: str, connection_string: str | None
) -> MeterProvider:
    """Export HTTP metrics with the same resource as the service's server spans."""
    readers: list[MetricReader] = []
    if connection_string:
        try:
            from azure.monitor.opentelemetry.exporter import AzureMonitorMetricExporter

            readers.append(
                PeriodicExportingMetricReader(
                    AzureMonitorMetricExporter(connection_string=connection_string)
                )
            )
        except (ValueError, OSError):
            logging.getLogger(__name__).warning(
                "Azure metric export could not be initialized; HTTP serving remains enabled"
            )
    return MeterProvider(
        resource=Resource.create({"service.name": service_name}), metric_readers=readers
    )