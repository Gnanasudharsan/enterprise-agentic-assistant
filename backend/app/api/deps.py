from fastapi import Request

from app.core.config import Settings
from app.llm.base import LLMClient


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client
