"""LLM client for any OpenAI-compatible chat completions API."""

from collections.abc import AsyncIterator, Sequence

import httpx2
import openai

from app.llm.base import ChatMessage, LLMError, LLMResult, LLMTimeoutError, StreamDelta


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
        self.model = model
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=max_retries,
            http_client=http_client,
        )

    def _request_args(self, messages: Sequence[ChatMessage]) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self._temperature,
            "max_tokens": self._max_output_tokens,
        }

    async def complete(
        self, messages: Sequence[ChatMessage], *, json_mode: bool = False
    ) -> LLMResult:
        args = self._request_args(messages)
        if json_mode:
            args["response_format"] = {"type": "json_object"}
            args["temperature"] = 0.0  # plans and SQL should be reproducible
        try:
            resp = await self._client.chat.completions.create(**args)
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

    async def stream(
        self, messages: Sequence[ChatMessage]
    ) -> AsyncIterator[StreamDelta | LLMResult]:
        parts: list[str] = []
        model = self.model
        prompt_tokens = completion_tokens = None
        try:
            chunks = await self._client.chat.completions.create(
                **self._request_args(messages),
                stream=True,
                stream_options={"include_usage": True},
            )
            async for chunk in chunks:
                model = chunk.model or model
                if chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    parts.append(text)
                    yield StreamDelta(text)
        except openai.APITimeoutError as exc:
            raise LLMTimeoutError("LLM request timed out") from exc
        except openai.APIError as exc:
            raise LLMError(f"LLM provider error: {type(exc).__name__}") from exc

        if not parts:
            raise LLMError("LLM returned an empty response")
        yield LLMResult(
            content="".join(parts),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def aclose(self) -> None:
        await self._client.close()
