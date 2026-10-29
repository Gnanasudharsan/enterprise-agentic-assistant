from app.core.config import Settings
from app.llm.base import LLMClient
from app.llm.fake import FakeLLMClient
from app.llm.openai_client import OpenAIChatClient


def build_llm_client(settings: Settings) -> LLMClient:
    if settings.resolved_llm_provider == "fake":
        return FakeLLMClient(stream_delay_seconds=0.01)
    assert settings.llm_api_key is not None  # guaranteed by resolved_llm_provider
    return OpenAIChatClient(
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
    )
