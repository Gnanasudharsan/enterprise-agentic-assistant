"""Usage metering (cost) and OpenTelemetry spans."""

import pytest
from langgraph.errors import GraphInterrupt
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core.telemetry import traced_node
from app.llm.base import LLMResult
from app.llm.metering import MeteredLLM, start_meter
from tests.conftest import StubLLM, make_chunk
from tests.test_agent_graph import GOOD_SQL, QUESTION, both_steps

_exporter = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def _tracer_provider():
    # The global provider can be set once per process; tracers created at import time
    # are proxies that pick it up.
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(_exporter))
    trace.set_tracer_provider(provider)


@pytest.fixture
def spans():
    _exporter.clear()
    return _exporter


def test_agent_run_counts_every_model_call(client, llm):
    llm.json_results = [both_steps(), GOOD_SQL]  # planner, SQL writer
    llm.result = LLMResult(content="Answer [T1].", model="stub-model", prompt_tokens=100,
                           completion_tokens=20)  # fmt: skip

    body = client.post("/api/v1/agent/run", json={"prompt": QUESTION}).json()

    # planner + SQL + analyst; only the analyst's stub reports tokens
    assert body["usage"] == {"prompt_tokens": 100, "completion_tokens": 20, "llm_calls": 3}
    stored = client.get(f"/api/v1/agent/runs/{body['run_id']}").json()
    assert stored["usage"] == body["usage"]


def test_chat_passes_retrieval_options(client, retriever):
    retriever.chunks = [make_chunk("HR-001", "PTO", "5 days carry over.")]
    client.post("/api/v1/chat", json={"prompt": "PTO?", "retrieval_mode": "vector",
                                       "rerank": False})  # fmt: skip
    client.post("/api/v1/chat", json={"prompt": "PTO?"})

    assert retriever.options == [
        {"mode": "vector", "rerank": False},
        {"mode": "hybrid", "rerank": None},  # None = the server's RERANKER setting
    ]


def test_chat_rejects_unknown_retrieval_mode(client):
    resp = client.post("/api/v1/chat", json={"prompt": "PTO?", "retrieval_mode": "magic"})
    assert resp.status_code == 422


async def test_meter_is_per_request():
    llm = MeteredLLM(StubLLM())
    first = start_meter()
    await llm.complete([])
    await llm.complete([])
    second = start_meter()
    await llm.complete([])

    assert (first.calls, first.prompt_tokens, first.completion_tokens) == (2, 20, 4)
    assert second.calls == 1
    assert first.by_model == {"stub-model": {"calls": 2, "prompt": 20, "completion": 4}}


async def test_streamed_calls_are_metered_and_traced(spans):
    llm = MeteredLLM(StubLLM())
    meter = start_meter()
    parts = [item async for item in llm.stream([])]

    assert isinstance(parts[-1], LLMResult)
    assert meter.calls == 1
    [span] = spans.get_finished_spans()
    assert span.attributes["gen_ai.usage.input_tokens"] == 10
    assert span.attributes["gen_ai.usage.output_tokens"] == 2


def test_agent_run_emits_node_and_llm_spans(client, llm, spans):
    llm.json_results = [both_steps(), GOOD_SQL]
    client.post("/api/v1/agent/run", json={"prompt": QUESTION})

    names = [s.name for s in spans.get_finished_spans()]
    for node in ("supervisor", "research", "data", "coordinator", "analyst"):
        assert f"agent.{node}" in names
    assert names.count("chat stub-model") == 3
    analyst = next(s for s in spans.get_finished_spans() if s.name == "agent.analyst")
    # Model calls nest under the node that made them.
    children = [s for s in spans.get_finished_spans() if s.parent and
                s.parent.span_id == analyst.context.span_id]  # fmt: skip
    assert [c.name for c in children] == ["chat stub-model"]
    # Spans carry identifiers and sizes, never the question or the answer.
    for s in spans.get_finished_spans():
        assert QUESTION not in str(dict(s.attributes or {}))


async def test_interrupt_is_not_an_error_span(spans):
    async def pause(state):
        raise GraphInterrupt(())

    with pytest.raises(GraphInterrupt):
        await traced_node("approval", pause)({"run_id": "r1"})

    [span] = spans.get_finished_spans()
    assert span.attributes["agent.interrupted"] is True
    assert span.attributes["agent.run_id"] == "r1"
    assert span.status.status_code == trace.StatusCode.UNSET


async def test_failed_node_span_records_the_error(spans):
    async def boom(state):
        raise ValueError("bad")

    with pytest.raises(ValueError):
        await traced_node("data", boom)({"step": {"id": "s2"}})

    [span] = spans.get_finished_spans()
    assert span.status.status_code == trace.StatusCode.ERROR
    assert span.attributes["agent.step_id"] == "s2"
