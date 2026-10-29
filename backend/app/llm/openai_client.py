"""LLM client for any OpenAI-compatible chat completions API."""

from collections.abc import Sequence

import httpx2
import openai

from app.llm.base import ChatMessage, LLMError, LLMResult, LLMTimeoutError


class OpenAIChatClient:
    provider = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
        max_retries: int,
        temperature: float,
        max_output_tokens: int,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=max_retries,
            http_client=http_client,
        )

    async def complete(self, messages: Sequence[ChatMessage]) -> LLMResult:
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=self._temperature,
                max_tokens=self._max_output_tokens,
            )
        except openai.APITimeoutError as exc:
            raise LLMTimeoutError("LLM request timed out") from exc
        except openai.APIError as exc:
            raise LLMError(f"LLM provider error: {type(exc).__name__}") from exc

        if not resp.choices or not resp.choices[0].message.content:
            raise LLMError("LLM returned an empty response")

        usage = resp.usage
        return LLMResult(
            content=resp.choices[0].message.content,
            model=resp.model,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
        )

    async def aclose(self) -> None:
        await self._client.close()
