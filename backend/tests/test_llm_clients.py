import json

import httpx2 as httpx  # the HTTP library openai>=3 is built on
import pytest

from app.core.config import Settings
from app.llm.base import ChatMessage, LLMError, LLMTimeoutError
from app.llm.factory import build_llm_client
from app.llm.fake import FakeLLMClient
from app.llm.openai_client import OpenAIChatClient

MESSAGES = [ChatMessage("system", "be helpful"), ChatMessage("user", "hello")]


def make_client(handler) -> OpenAIChatClient:
    return OpenAIChatClient(
        api_key="test-key",
        model="gpt-test",
        base_url="https://llm.test/v1",
        timeout_seconds=5,
        max_retries=0,
        temperature=0.2,
        max_output_tokens=64,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def completion(content: str | None) -> dict:
    return {
        "id": "cmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-test",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    }


async def test_openai_client_parses_completion():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json=completion("hi there"))

    client = make_client(handler)
    result = await client.complete(MESSAGES)

    assert result.content == "hi there"
    assert (result.prompt_tokens, result.completion_tokens) == (7, 3)
    assert seen["url"] == "https://llm.test/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["model"] == "gpt-test"
    assert seen["body"]["messages"][1] == {"role": "user", "content": "hello"}
    await client.aclose()


async def test_openai_client_wraps_http_errors():
    client = make_client(lambda r: httpx.Response(500, json={"error": {"message": "boom"}}))
    with pytest.raises(LLMError):
        await client.complete(MESSAGES)


async def test_openai_client_wraps_timeouts():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    client = make_client(handler)
    with pytest.raises(LLMTimeoutError):
        await client.complete(MESSAGES)


async def test_openai_client_rejects_empty_content():
    client = make_client(lambda r: httpx.Response(200, json=completion(None)))
    with pytest.raises(LLMError, match="empty"):
        await client.complete(MESSAGES)


async def test_fake_client_is_deterministic():
    fake = FakeLLMClient()
    a, b = await fake.complete(MESSAGES), await fake.complete(MESSAGES)
    assert a == b
    assert "hello" in a.content


def test_factory_selects_provider():
    assert isinstance(build_llm_client(Settings(_env_file=None)), FakeLLMClient)
    s = Settings(_env_file=None, llm_provider="openai", llm_api_key="k")
    assert isinstance(build_llm_client(s), OpenAIChatClient)
