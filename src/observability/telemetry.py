"""
OpenTelemetry instrumentation for the Personal Knowledge Assistant.

Configures a ``TracerProvider`` with optional exporters controlled by
environment variables:

  OTEL_EXPORTER_OTLP_ENDPOINT
      gRPC endpoint for an OTLP-compatible collector (e.g. Jaeger, Tempo,
      Honeycomb).  Example: ``http://localhost:4317``.
      Requires ``opentelemetry-exporter-otlp-proto-grpc`` to be installed.

  OTEL_CONSOLE_EXPORT
      Set to ``"true"`` to print every span to stdout — useful for local
      debugging without a collector.  Default: ``"false"``.

If neither variable is set the provider runs in no-op mode: spans are created
but not exported, so the application works normally without any telemetry
infrastructure.

Typical usage in an agent::

    from opentelemetry.trace import Status, StatusCode
    from src.observability.telemetry import get_tracer

    def my_agent(state):
        tracer = get_tracer()
        with tracer.start_as_current_span("my_agent") as span:
            span.set_attribute("query.length", len(state["query"]))
            # ... work ...
            span.set_attribute("result.count", n)
            return result
"""
import logging
import os
from functools import lru_cache

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

logger = logging.getLogger(__name__)

_SERVICE_NAME = "personal-knowledge-assistant"
_SERVICE_VERSION = "1.0.0"


def _build_provider() -> TracerProvider:
    """Construct and register the global ``TracerProvider``."""
    resource = Resource.create(
        {
            "service.name": _SERVICE_NAME,
            "service.version": _SERVICE_VERSION,
        }
    )
    provider = TracerProvider(resource=resource)

    # ── Console exporter ──────────────────────────────────────────────────────
    if os.getenv("OTEL_CONSOLE_EXPORT", "false").lower() == "true":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("[Telemetry] Console span exporter enabled.")

    # ── OTLP / gRPC exporter ─────────────────────────────────────────────────
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # noqa: PLC0415
                OTLPSpanExporter,
            )

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
            )
            logger.info("[Telemetry] OTLP exporter configured → %s", otlp_endpoint)
        except ImportError:
            logger.warning(
                "[Telemetry] opentelemetry-exporter-otlp-proto-grpc is not installed. "
                "Run: pip install opentelemetry-exporter-otlp-proto-grpc"
            )

    trace.set_tracer_provider(provider)
    return provider


@lru_cache(maxsize=1)
def get_tracer() -> trace.Tracer:
    """
    Return the singleton ``Tracer`` for this service.

    The ``TracerProvider`` is initialised on first call (lazy) so that
    environment variables from ``.env`` are already loaded by the time
    the exporter is configured.
    """
    _build_provider()
    return trace.get_tracer(_SERVICE_NAME)
