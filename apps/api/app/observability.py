from __future__ import annotations

import logging

from app.core.config import Settings

logger = logging.getLogger("planproof")


def configure_observability(settings: Settings, app) -> None:
    """Enable OTel when configured, while keeping local/test runs dependency-light."""
    if not settings.otel_exporter_otlp_endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning("otel_unavailable", extra={"service": settings.otel_service_name})
        return
    provider = TracerProvider(Resource.create({"service.name": settings.otel_service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=str(settings.otel_exporter_otlp_endpoint)))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
