import pytest

from app.llm.base import LLMError, LLMTimeoutError


def test_chat_returns_answer(client, llm):
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


@pytest.mark.parametrize("prompt", ["", "   ", "x" * 8001])
def test_chat_rejects_invalid_prompt(client, llm, prompt):
    resp = client.post("/api/v1/chat", json={"prompt": prompt})
    assert resp.status_code == 422
    assert llm.calls == []


def test_chat_maps_timeout_to_504(client, llm):
    llm.error = LLMTimeoutError("slow")
    resp = client.post("/api/v1/chat", json={"prompt": "hi"})
    assert resp.status_code == 504


def test_chat_maps_provider_error_to_502_without_leaking_details(client, llm):
    llm.error = LLMError("secret internal detail")
    resp = client.post("/api/v1/chat", json={"prompt": "hi"})
    assert resp.status_code == 502
    assert "secret" not in resp.text


def test_llm_client_closed_on_shutdown(app, llm):
    from fastapi.testclient import TestClient

    with TestClient(app):
        pass
    assert llm.closed
