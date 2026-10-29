"""Typed application settings, loaded from environment variables and `.env`."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # "fake" returns deterministic answers without network calls (local demos, CI).
    llm_provider: Literal["openai", "fake"] = "fake"
    llm_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_max_output_tokens: int = Field(default=1024, gt=0)
    llm_system_prompt: str = (
        "You are an enterprise research assistant. Answer clearly and concisely. "
        "If you do not know something, say so instead of guessing."
    )

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
        return self

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
