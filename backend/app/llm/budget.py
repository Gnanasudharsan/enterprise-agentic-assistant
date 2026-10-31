"""A daily token budget for deployed demos.

`BudgetedLLM` sends calls to the real model until the day's budget (tokens across all
requests, UTC day) is spent, then to the offline fake model, so the demo keeps working
at no cost instead of failing. The count starts from the day's recorded runs at startup,
so a restart does not reset it.
"""

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import AgentRun, ChatRun
from app.llm.base import ChatMessage, LLMClient, LLMResult, StreamDelta


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


class DailyBudget:
    def __init__(self, limit_tokens: int) -> None:
        self.limit = limit_tokens
        self.day = _today()
        self.used = 0

    def _roll(self) -> None:
        if (today := _today()) != self.day:
            self.day, self.used = today, 0

    def add(self, result: LLMResult) -> None:
        self._roll()
        self.used += (result.prompt_tokens or 0) + (result.completion_tokens or 0)

    @property
    def exhausted(self) -> bool:
        self._roll()
        return self.limit > 0 and self.used >= self.limit

    async def load(self, sessionmaker: async_sessionmaker) -> None:
        """Count what today's recorded runs already used."""
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        async with sessionmaker() as db:
            used = 0
            for model in (ChatRun, AgentRun):
                tokens = func.coalesce(model.prompt_tokens, 0) + func.coalesce(
                    model.completion_tokens, 0
                )
                used += (
                    await db.scalar(
                        select(func.coalesce(func.sum(tokens), 0)).where(model.created_at >= start)
                    )
                    or 0
                )
        self.day, self.used = _today(), int(used)


class BudgetedLLM:
    def __init__(self, real: LLMClient, fallback: LLMClient, budget: DailyBudget) -> None:
        self.real = real
        self.fallback = fallback
        self.budget = budget

    @property
    def _active(self) -> LLMClient:
        return self.fallback if self.budget.exhausted else self.real

    @property
    def provider(self) -> str:
        return self._active.provider

    @property
    def model(self) -> str:
        return self._active.model

    async def complete(
        self, messages: Sequence[ChatMessage], *, json_mode: bool = False
    ) -> LLMResult:
        client = self._active
        result = await client.complete(messages, json_mode=json_mode)
        if client is self.real:
            self.budget.add(result)
        return result

    async def stream(
        self, messages: Sequence[ChatMessage]
    ) -> AsyncIterator[StreamDelta | LLMResult]:
        client = self._active
        async for item in client.stream(messages):
            if isinstance(item, LLMResult) and client is self.real:
                self.budget.add(item)
            yield item

    async def aclose(self) -> None:
        await self.real.aclose()
        await self.fallback.aclose()
