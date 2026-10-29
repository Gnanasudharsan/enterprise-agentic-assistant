"""Typed application settings, loaded from environment variables and `.env`."""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SYSTEM_PROMPT = """\
You are the Enterprise Research Assistant, an AI assistant for employees of a software company.

How to answer:
- Lead with the direct answer, then supporting detail. Be specific and practical.
- Use Markdown: short paragraphs, bullet or numbered lists for steps, **bold** for key terms,
  and tables when comparing options. Use headings only for longer answers.
- Match length to the question: a sentence or two for simple questions, a structured answer
  for complex ones. Do not pad.
- Ask one clarifying question only when the request is genuinely ambiguous.

Honesty rules:
- You only know this company's internal documents when they are given to you as sources in
  this conversation. You cannot access databases or tools yet. When an answer depends on
  company-specific policy or data that is not in the sources, say so, give sound general
  guidance, and suggest confirming it against internal policy.
- Never invent company facts, numbers, names, policy details, or citations.
- If you are unsure, say so.
"""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Look in the backend dir and the repo root so `.env` works from either.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "Enterprise Agentic Assistant"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173"]

    # --- LLM ---
    # "auto" uses the real provider when an API key is available, otherwise "fake".
    # "fake" returns canned answers without network calls (local demos, CI).
    llm_provider: Literal["auto", "openai", "fake"] = "auto"
    llm_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("llm_api_key", "openai_api_key")
    )
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)
    llm_temperature: float = Field(default=0.3, ge=0, le=2)
    llm_max_output_tokens: int = Field(default=1500, gt=0)
    llm_system_prompt: str = DEFAULT_SYSTEM_PROMPT

    # --- Retrieval (RAG) ---
    # "auto" uses OpenAI embeddings when an API key is available, else the offline
    # hashing embedder. Changing the embedder re-embeds documents on next ingestion.
    embedding_provider: Literal["auto", "openai", "hashing"] = "auto"
    embedding_model: str = "text-embedding-3-small"
    retrieval_top_k: int = Field(default=6, ge=1, le=20)
    retrieval_candidates: int = Field(default=20, ge=1, le=100)  # per channel, before fusion
    rrf_k: int = Field(default=60, ge=1)
    reranker: Literal["none", "llm"] = "none"
    # Groups of the (single, demo) user until authentication lands. Retrieval only
    # returns chunks from documents whose ACL overlaps these groups.
    user_groups: list[str] = ["all-employees"]
    documents_dir: str = "../datasets/documents"

    # --- Database ---
    database_url: str | None = None
    postgres_user: str = "assistant"
    postgres_password: SecretStr = SecretStr("change-me")
    postgres_db: str = "assistant"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    @model_validator(mode="after")
    def _check_llm_credentials(self) -> "Settings":
        if self.llm_provider == "openai" and not self.llm_api_key:
            raise ValueError("LLM_API_KEY is required when LLM_PROVIDER=openai")
        if self.embedding_provider == "openai" and not self.llm_api_key:
            raise ValueError("LLM_API_KEY is required when EMBEDDING_PROVIDER=openai")
        return self

    @property
    def resolved_llm_provider(self) -> Literal["openai", "fake"]:
        if self.llm_provider == "auto":
            return "openai" if self.llm_api_key else "fake"
        return self.llm_provider

    @property
    def resolved_embedding_provider(self) -> Literal["openai", "hashing"]:
        if self.embedding_provider == "auto":
            return "openai" if self.llm_api_key else "hashing"
        return self.embedding_provider

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
