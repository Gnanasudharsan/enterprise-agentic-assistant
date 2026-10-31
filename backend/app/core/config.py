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
    # Hosts that answers and drafted issues may link to. Images are always removed and
    # other links are reduced to their text, so injected content cannot exfiltrate data
    # through a URL (see app.rag.grounding.sanitize_links).
    answer_link_hosts: list[str] = []

    # --- Agents (multi-agent orchestration) ---
    agent_max_plan_steps: int = Field(default=4, ge=1, le=6)
    agent_max_plan_attempts: int = Field(default=2, ge=1, le=4)  # planner JSON repair
    agent_max_sql_attempts: int = Field(default=3, ge=1, le=5)  # SQL repair loop per step
    # "postgres" checkpoints every graph step (interrupted runs can be resumed);
    # "memory" keeps checkpoints in-process (tests, demos without a database).
    agent_checkpointer: Literal["postgres", "memory"] = "postgres"
    sql_timeout_ms: int = Field(default=5000, ge=100, le=60000)
    sql_max_rows: int = Field(default=200, ge=1, le=5000)

    # --- Actions (MCP tools behind approval) ---
    actions_enabled: bool = True
    # The tracker MCP server runs as a subprocess and receives only these settings.
    tracker_backend: Literal["local", "github"] = "local"
    tracker_db_path: str = "data/tracker.sqlite3"
    github_repo: str | None = None  # "owner/name"
    # Fine-grained token for that repository, with only "Issues: read and write".
    github_token: SecretStr | None = None
    # Which access groups may use each tool. Tools not listed here are denied, and every
    # tool not in READ_ONLY_TOOLS (app.actions.policy) needs a human approval to run.
    action_permissions: dict[str, list[str]] = {
        "create_issue": ["all-employees"],
        "search_issues": ["all-employees"],
    }
    # The demo caller's identity, recorded on approvals, until authentication lands.
    user_id: str = "demo-user"

    # --- Observability ---
    # "otlp" exports OpenTelemetry traces to OTEL_EXPORTER_OTLP_ENDPOINT (e.g. Jaeger);
    # "console" prints them. LangSmith tracing of the graph is separate: set
    # LANGSMITH_TRACING=true and LANGSMITH_API_KEY.
    tracing: Literal["none", "otlp", "console", "gcp"] = "none"
    otel_service_name: str = "enterprise-assistant-api"

    # --- Deployment ---
    # Serve the built frontend from this directory (the production image sets it).
    static_dir: str | None = None
    log_format: Literal["text", "json"] = "text"  # json: one object per line (Cloud Logging)
    # Visitors must send this code (the UI asks for it). Unset: no code required.
    access_code: SecretStr | None = None
    # Model-calling requests per client per window; 0 disables the limit.
    rate_limit_requests: int = Field(default=0, ge=0)
    rate_limit_window_seconds: int = Field(default=600, ge=1)
    # Tokens per UTC day across all requests before answers switch to the offline model;
    # 0 disables the budget.
    daily_token_budget: int = Field(default=0, ge=0)
    # Proxies in front of the app that append to X-Forwarded-For (Cloud Run: 1).
    forwarded_hops: int = Field(default=0, ge=0, le=5)
    db_pool_size: int = Field(default=5, ge=1, le=50)

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
        if self.tracker_backend == "github" and not (self.github_repo and self.github_token):
            raise ValueError(
                "GITHUB_REPO and GITHUB_TOKEN are required when TRACKER_BACKEND=github"
            )
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
    def psycopg_url(self) -> str:
        """The same database as a libpq URL, for the LangGraph checkpointer (psycopg)."""
        return self.sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://", 1)

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
