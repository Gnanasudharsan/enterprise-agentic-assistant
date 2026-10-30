"""Offline LLM for local demos and CI. Makes no network calls."""

import asyncio
import re
from collections.abc import AsyncIterator, Sequence

from app.llm.base import ChatMessage, LLMResult, StreamDelta

_TABLE = re.compile(r'<table id="(T\d+)" title="([^"]*)" rows="(\d+)')
_SOURCE = re.compile(
    r'<source id="(S\d+)" doc="([^"]*)" location="([^"]*)">\n(.*?)\n</source>', re.S
)

DEMO_ANSWER = """\
**Demo mode:** no language model is connected yet, so I can't write a real answer.

You asked:
> {prompt}

{retrieval}

To get real answers, connect a model in one of these ways:

1. Export `OPENAI_API_KEY` in your shell. The backend picks it up automatically.
2. Or set `LLM_API_KEY` (and optionally `LLM_MODEL`, `LLM_BASE_URL`) in `.env`.

Then restart the backend with `docker compose up -d --build`.
"""


class FakeLLMClient:
    provider = "fake"
    model = "demo-offline"

    def __init__(self, stream_delay_seconds: float = 0.0) -> None:
        self._delay = stream_delay_seconds

    def _answer(self, messages: Sequence[ChatMessage]) -> LLMResult:
        prompt = next(m.content for m in reversed(messages) if m.role == "user")
        sources = [
            m for msg in messages if msg.role == "system" for m in _SOURCE.findall(msg.content)
        ]
        if sources:
            sid, doc, location, content = sources[0]
            excerpt = " ".join(content.split())[:280]
            retrieval = (
                f"Knowledge-base search still works. The most relevant passage is from "
                f"**{doc}** ({location}) [{sid}]:\n\n> {excerpt}…"
            )
        else:
            retrieval = "No knowledge-base passages were provided for this question."
        tables = [
            t for msg in messages if msg.role == "system" for t in _TABLE.findall(msg.content)
        ]
        if tables:
            tid, title, rows = tables[0]
            retrieval += (
                f"\n\nThe data agent also ran a reviewed query, **{title}** ({rows} rows) [{tid}]. "
                "See the table and chart with this answer."
            )
        answer = DEMO_ANSWER.format(prompt=prompt.replace("\n", "\n> "), retrieval=retrieval)
        return LLMResult(
            content=answer,
            model=self.model,
            prompt_tokens=sum(len(m.content.split()) for m in messages),
            completion_tokens=len(answer.split()),
        )

    async def complete(
        self, messages: Sequence[ChatMessage], *, json_mode: bool = False
    ) -> LLMResult:
        if json_mode:
            # No model to plan or write SQL: callers fall back to deterministic behavior.
            return LLMResult(content="{}", model=self.model, prompt_tokens=0, completion_tokens=0)
        return self._answer(messages)

    async def stream(
        self, messages: Sequence[ChatMessage]
    ) -> AsyncIterator[StreamDelta | LLMResult]:
        result = self._answer(messages)
        # Emit word-by-word (keeping whitespace) so the UI's streaming path is exercised.
        for token in re.findall(r"\S+\s*|\s+", result.content):
            if self._delay:
                await asyncio.sleep(self._delay)
            yield StreamDelta(token)
        yield result

    async def aclose(self) -> None:
        return None
