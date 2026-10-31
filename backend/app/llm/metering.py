"""Per-request accounting of LLM calls and tokens, and a tracing span per call.

`MeteredLLM` wraps the configured client once at startup. Every call adds to the
`UsageMeter` of the current request (a context variable set by the chat route or the
agent service), so a run's cost includes the planner, SQL repair, reranker, analyst,
and action drafts, not just the final answer. Concurrent graph nodes run in copies of
the request's context, which share the same meter object.
"""

from collections.abc import AsyncIterator, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from opentelemetry import trace

from app.llm.base import ChatMessage, LLMClient, LLMResult, StreamDelta

tracer = trace.get_tracer("app.llm")


@dataclass
class UsageMeter:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)

    def add(self, result: LLMResult) -> None:
        self.calls += 1
        self.prompt_tokens += result.prompt_tokens or 0
        self.completion_tokens += result.completion_tokens or 0
        model = self.by_model.setdefault(result.model, {"calls": 0, "prompt": 0, "completion": 0})
        model["calls"] += 1
        model["prompt"] += result.prompt_tokens or 0
        model["completion"] += result.completion_tokens or 0


_meter: ContextVar[UsageMeter | None] = ContextVar("llm_usage_meter", default=None)


def start_meter() -> UsageMeter:
    """Start counting for the current request; calls outside any request are not counted."""
    meter = UsageMeter()
    _meter.set(meter)
    return meter


def _record(span: trace.Span, result: LLMResult) -> None:
    meter = _meter.get()
    if meter is not None:
        meter.add(result)
    span.set_attribute("gen_ai.response.model", result.model)
    if result.prompt_tokens is not None:
        span.set_attribute("gen_ai.usage.input_tokens", result.prompt_tokens)
    if result.completion_tokens is not None:
        span.set_attribute("gen_ai.usage.output_tokens", result.completion_tokens)


class MeteredLLM:
    def __init__(self, inner: LLMClient) -> None:
        self.inner = inner

    # Read through: a budgeted client switches to the offline model when the budget is spent.
    @property
    def provider(self) -> str:
        return self.inner.provider

    @property
    def model(self) -> str:
        return self.inner.model

    def __getattr__(self, name: str) -> Any:  # test stubs expose extra attributes
        return getattr(self.inner, name)

    def _attributes(self, json_mode: bool = False) -> dict[str, Any]:
        return {
            "gen_ai.operation.name": "chat",
            "gen_ai.system": self.provider,
            "gen_ai.request.model": self.model,
            "app.llm.json_mode": json_mode,
        }

    async def complete(
        self, messages: Sequence[ChatMessage], *, json_mode: bool = False
    ) -> LLMResult:
        with tracer.start_as_current_span(
            f"chat {self.model}", kind=trace.SpanKind.CLIENT, attributes=self._attributes(json_mode)
        ) as span:
            result = await self.inner.complete(messages, json_mode=json_mode)
            _record(span, result)
            return result

    async def stream(
        self, messages: Sequence[ChatMessage]
    ) -> AsyncIterator[StreamDelta | LLMResult]:
        # Not made the current span: a generator may resume in another context, and
        # detaching a context there fails. Nothing nests under a streamed call anyway.
        span = tracer.start_span(
            f"chat {self.model}", kind=trace.SpanKind.CLIENT, attributes=self._attributes()
        )
        try:
            async for item in self.inner.stream(messages):
                if isinstance(item, LLMResult):
                    _record(span, item)
                yield item
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise
        finally:
            span.end()

    async def aclose(self) -> None:
        await self.inner.aclose()
