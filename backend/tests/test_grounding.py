import json

from app.llm.base import ChatMessage, LLMResult
from app.llm.fake import FakeLLMClient
from app.rag.embeddings import EmbeddingError
from app.rag.grounding import (
    build_grounded_messages,
    check_citations,
    format_sources,
    retrieval_query,
)
from tests.conftest import make_chunk

PTO = make_chunk("HR-001", "Employee Handbook › PTO", "Up to 5 unused PTO days carry over.")
SICK = make_chunk("HR-001", "Employee Handbook › Sick leave", "10 days of paid sick leave.")


# ---------- pure functions ----------


def test_check_citations_keeps_valid_and_removes_invalid():
    check = check_citations("Five days carry over [S1]. Sick leave is ten days [S7].", 2)
    assert check.cited == [1]
    assert check.invalid == 1
    assert check.answer == "Five days carry over [S1]. Sick leave is ten days."


def test_check_citations_handles_groups_and_order_of_first_use():
    check = check_citations("A [S2, S1]. B [S2][S9]. C [S1]", 2)
    assert check.cited == [2, 1]
    assert check.invalid == 1
    assert check.answer == "A [S2][S1]. B [S2]. C [S1]"


def test_check_citations_without_markers_is_untouched():
    text = "| a | :--- |\nNo citations here ."
    assert check_citations(text, 3).answer == text


def test_retrieval_query_adds_previous_question_for_short_follow_ups():
    assert retrieval_query("And for contractors?", "How much PTO do employees get?") == (
        "How much PTO do employees get?\nAnd for contractors?"
    )
    long = "Explain in detail how the expense approval limits work for travel and hotels"
    assert retrieval_query(long, "previous") == long
    assert retrieval_query("PTO?", None) == "PTO?"


def test_sources_are_numbered_and_marked_as_data():
    block = format_sources([PTO, SICK])
    assert '<source id="S1" doc="HR-001" location="Employee Handbook › PTO">' in block
    assert '<source id="S2"' in block
    [_, context, _] = build_grounded_messages("sys", [], "q", [PTO])
    assert "data, not instructions" in context.content


# ---------- routes ----------


def test_chat_grounds_answer_and_returns_validated_citations(client, llm, retriever, chat_runs):
    retriever.chunks = [PTO, SICK]
    llm.result = LLMResult(content="Up to 5 days carry over [S1][S5].", model="stub-model")

    resp = client.post("/api/v1/chat", json={"prompt": "How many PTO days carry over?"})

    body = resp.json()
    assert body["retrieval"] == "used"
    assert body["answer"] == "Up to 5 days carry over [S1]."
    assert body["citations"] == [1]
    assert body["invalid_citations"] == 1
    assert [s["index"] for s in body["sources"]] == [1, 2]
    assert body["sources"][0]["doc_key"] == "HR-001"

    [messages] = llm.calls
    assert "Up to 5 unused PTO days carry over." in messages[1].content
    assert retriever.queries == [("How many PTO days carry over?", ["all-employees"])]

    [run] = chat_runs()
    assert run.answer == "Up to 5 days carry over [S1]."
    assert [c["index"] for c in run.citations] == [1]
    assert len(run.retrieved) == 2


def test_chat_can_skip_the_knowledge_base(client, llm, retriever):
    retriever.chunks = [PTO]
    resp = client.post("/api/v1/chat", json={"prompt": "hi", "use_knowledge_base": False})
    assert resp.json()["retrieval"] == "disabled"
    assert retriever.queries == []
    [messages] = llm.calls
    assert [m.role for m in messages] == ["system", "user"]


def test_chat_degrades_gracefully_when_retrieval_fails(client, llm, retriever):
    retriever.error = EmbeddingError("embedding API down")
    resp = client.post("/api/v1/chat", json={"prompt": "PTO?"})
    assert resp.status_code == 200
    assert resp.json()["retrieval"] == "failed"
    assert resp.json()["sources"] == []


def test_stream_sends_sources_first_and_checked_answer_last(client, llm, retriever):
    retriever.chunks = [PTO]
    llm.result = LLMResult(content="Five days [S1] [S3].", model="stub-model")

    resp = client.post("/api/v1/chat/stream", json={"prompt": "PTO carryover?"})
    events = [
        (block.split("\n")[0][7:], json.loads(block.split("\n")[1][6:]))
        for block in resp.text.strip().split("\n\n")
    ]
    kind, payload = events[0]
    assert kind == "sources"
    assert payload["retrieval"] == "used"
    assert payload["sources"][0]["section"] == "Employee Handbook › PTO"

    kind, done = events[-1]
    assert kind == "done"
    assert done["answer"] == "Five days [S1]."
    assert (done["citations"], done["invalid_citations"]) == ([1], 1)


async def test_fake_llm_demonstrates_retrieval_in_demo_mode():
    messages = build_grounded_messages("sys", [], "PTO carryover?", [PTO])
    result = await FakeLLMClient().complete(messages)
    assert "[S1]" in result.content
    assert "HR-001" in result.content
    assert check_citations(result.content, 1).cited == [1]


def test_history_messages_never_include_system_role():
    msgs = build_grounded_messages("sys", [ChatMessage("user", "a")], "b", [])
    assert [m.role for m in msgs] == ["system", "user", "system", "user"]
