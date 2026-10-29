import pytest
from fastapi.testclient import TestClient

from app.llm.base import LLMError, LLMTimeoutError


def test_chat_returns_answer_and_persists_run(client, llm, chat_runs):
    resp = client.post("/api/v1/chat", json={"prompt": "  What is our PTO policy?  "})

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "stub answer"
    assert body["provider"] == "stub"
    assert body["model"] == "stub-model"
    assert body["usage"] == {"prompt_tokens": 10, "completion_tokens": 2}
    assert isinstance(body["latency_ms"], int)

    [messages] = llm.calls
    assert [m.role for m in messages] == ["system", "user"]
    assert messages[1].content == "What is our PTO policy?"  # stripped

    [run] = chat_runs()
    assert str(run.id) == body["run_id"]
    assert run.status == "succeeded"
    assert run.prompt == "What is our PTO policy?"
    assert run.answer == "stub answer"
    assert (run.prompt_tokens, run.completion_tokens) == (10, 2)


@pytest.mark.parametrize("prompt", ["", "   ", "x" * 8001])
def test_chat_rejects_invalid_prompt(client, llm, chat_runs, prompt):
    resp = client.post("/api/v1/chat", json={"prompt": prompt})
    assert resp.status_code == 422
    assert llm.calls == []
    assert chat_runs() == []


def test_chat_maps_timeout_to_504_and_records_failure(client, llm, chat_runs):
    llm.error = LLMTimeoutError("slow")
    resp = client.post("/api/v1/chat", json={"prompt": "hi"})
    assert resp.status_code == 504

    [run] = chat_runs()
    assert (run.status, run.error_type, run.answer) == ("failed", "LLMTimeoutError", None)


def test_chat_maps_provider_error_to_502_without_leaking_details(client, llm):
    llm.error = LLMError("secret internal detail")
    resp = client.post("/api/v1/chat", json={"prompt": "hi"})
    assert resp.status_code == 502
    assert "secret" not in resp.text


def test_llm_client_closed_on_shutdown(app, llm):
    with TestClient(app):
        pass
    assert llm.closed
