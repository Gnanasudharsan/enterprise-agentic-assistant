"""OpenTelemetry tracing: one trace per request, with spans for graph nodes, LLM calls,
retrieval, SQL, and MCP tool calls.

Off by default (the API's no-op tracer costs nothing). `TRACING=otlp` exports over
OTLP/HTTP to `OTEL_EXPORTER_OTLP_ENDPOINT` (Jaeger, Grafana Tempo, Honeycomb, ...);
`TRACING=console` prints spans, for debugging. Span attributes carry ids, sizes,
timings, and token counts, never prompts, answers, or query results.
"""

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI
from langgraph.errors import GraphInterrupt
from opentelemetry import trace

from app import __version__
from app.core.config import Settings

logger = logging.getLogger(__name__)

tracer = trace.get_tracer("app.agents")


def setup_tracing(app: FastAPI, settings: Settings) -> None:
    if settings.tracing == "none":
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    provider = TracerProvider(
        resource=Resource.create(
            {"service.name": settings.otel_service_name, "service.version": __version__}
        )
    )
    if settings.tracing == "otlp":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter()  # reads OTEL_EXPORTER_OTLP_ENDPOINT / _HEADERS
    else:
        exporter = ConsoleSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    # Health checks would drown out real requests.
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,api/v1/health")
    logger.info("Tracing enabled (%s)", settings.tracing)


def traced_node(name: str, fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Wrap a graph node in a span. An approval interrupt is a pause, not an error."""

    @functools.wraps(fn)
    async def wrapper(state: Any, *args: Any, **kwargs: Any) -> Any:
        with tracer.start_as_current_span(
            f"agent.{name}", record_exception=False, set_status_on_exception=False
        ) as span:
            span.set_attribute("agent.node", name)
            if isinstance(state, dict):
                if run_id := state.get("run_id"):
                    span.set_attribute("agent.run_id", run_id)
                if step := state.get("step"):
                    span.set_attribute("agent.step_id", step.get("id", ""))
            try:
                return await fn(state, *args, **kwargs)
            except GraphInterrupt:
                span.set_attribute("agent.interrupted", True)
                raise
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(trace.Status(trace.StatusCode.ERROR, type(exc).__name__))
                raise

    return wrapper
