from collections.abc import Sequence

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.llm.base import ChatMessage, LLMResult
from app.main import create_app


class StubLLM:
    """Records calls and returns a canned result (or raises a canned error)."""

    provider = "stub"

    def __init__(self) -> None:
        self.result = LLMResult(
            content="stub answer", model="stub-model", prompt_tokens=10, completion_tokens=2
        )
        self.error: Exception | None = None
        self.calls: list[list[ChatMessage]] = []
        self.closed = False

    async def complete(self, messages: Sequence[ChatMessage]) -> LLMResult:
        self.calls.append(list(messages))
        if self.error:
            raise self.error
        return self.result

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def settings() -> Settings:
    # _env_file=None keeps a developer's local .env from leaking into tests.
    return Settings(_env_file=None, app_env="test", llm_provider="fake")


@pytest.fixture
def llm() -> StubLLM:
    return StubLLM()


@pytest.fixture
def app(settings: Settings, llm: StubLLM) -> FastAPI:
    app = create_app(settings)
    app.state.llm_client = llm
    return app


@pytest.fixture
def client(app: FastAPI):
    with TestClient(app) as c:
        yield c
