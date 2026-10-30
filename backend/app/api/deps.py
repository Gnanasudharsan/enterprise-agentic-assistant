from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.service import AgentService
from app.core.config import Settings
from app.llm.base import LLMClient
from app.rag.retrieval import Retriever


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def get_retriever(request: Request) -> Retriever:
    return request.app.state.retriever


def get_user_groups(request: Request) -> list[str]:
    """The caller's access groups. Single demo identity until authentication lands."""
    return request.app.state.settings.user_groups


def get_agent_service(request: Request) -> AgentService:
    return request.app.state.agent_service
