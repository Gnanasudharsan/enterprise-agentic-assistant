"""Provider-agnostic LLM interface.

Routes and agents depend on `LLMClient`, never on a vendor SDK, so providers can be
swapped (or faked in tests) without touching business logic.
"""

from collections.abc import AsyncIterator, Sequence
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


@dataclass(frozen=True)
class StreamDelta:
    """A fragment of generated text, emitted while streaming."""

    text: str


class LLMError(Exception):
    """The provider failed or returned an unusable response."""


class LLMTimeoutError(LLMError):
    """The provider did not respond within the configured timeout."""


class LLMClient(Protocol):
    provider: str
    model: str

    async def complete(
        self, messages: Sequence[ChatMessage], *, json_mode: bool = False
    ) -> LLMResult:
        """`json_mode` asks the provider to return a single JSON object (the prompt must
        still describe the expected shape). Callers validate the result themselves."""
        ...

    def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[StreamDelta | LLMResult]:
        """Yield `StreamDelta`s as text is generated, then exactly one final `LLMResult`."""
        ...

    async def aclose(self) -> None: ...
