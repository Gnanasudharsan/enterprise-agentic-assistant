"""Provider-agnostic LLM interface.

Routes and agents depend on `LLMClient`, never on a vendor SDK, so providers can be
swapped (or faked in tests) without touching business logic.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class LLMResult:
    content: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMError(Exception):
    """The provider failed or returned an unusable response."""


class LLMTimeoutError(LLMError):
    """The provider did not respond within the configured timeout."""


class LLMClient(Protocol):
    provider: str

    async def complete(self, messages: Sequence[ChatMessage]) -> LLMResult: ...

    async def aclose(self) -> None: ...
