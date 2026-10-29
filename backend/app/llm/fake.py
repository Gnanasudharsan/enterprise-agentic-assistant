"""Deterministic offline LLM for local demos and CI. Makes no network calls."""

from collections.abc import Sequence

from app.llm.base import ChatMessage, LLMResult


class FakeLLMClient:
    provider = "fake"
    model = "fake-echo-1"

    async def complete(self, messages: Sequence[ChatMessage]) -> LLMResult:
        prompt = next(m.content for m in reversed(messages) if m.role == "user")
        answer = (
            f'[fake-llm] You asked: "{prompt}". '
            "Set LLM_PROVIDER=openai and LLM_API_KEY to get real answers."
        )
        return LLMResult(
            content=answer,
            model=self.model,
            prompt_tokens=sum(len(m.content.split()) for m in messages),
            completion_tokens=len(answer.split()),
        )

    async def aclose(self) -> None:
        return None
