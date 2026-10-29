import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_openai_provider_requires_api_key():
    with pytest.raises(ValidationError, match="LLM_API_KEY is required"):
        Settings(_env_file=None, llm_provider="openai", llm_api_key=None)


def test_database_url_built_from_parts():
    s = Settings(_env_file=None, postgres_user="u", postgres_password="p", postgres_host="db")
    assert s.sqlalchemy_url == "postgresql+asyncpg://u:p@db:5432/assistant"


def test_explicit_database_url_wins():
    s = Settings(_env_file=None, database_url="sqlite+aiosqlite:///:memory:")
    assert s.sqlalchemy_url == "sqlite+aiosqlite:///:memory:"
