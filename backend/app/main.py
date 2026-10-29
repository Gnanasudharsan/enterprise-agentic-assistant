"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import chat, documents, health, search
from app.core.config import Settings, get_settings
from app.db.session import build_engine, build_sessionmaker
from app.llm.factory import build_llm_client
from app.rag.factory import build_embedder, build_retriever


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Tests may pre-populate app.state.llm_client / retriever with stubs.
        if getattr(app.state, "llm_client", None) is None:
            app.state.llm_client = build_llm_client(settings)
        if getattr(app.state, "retriever", None) is None:
            embedder = build_embedder(settings)
            app.state.retriever = build_retriever(settings, embedder, app.state.llm_client)
        app.state.engine = build_engine(settings.sqlalchemy_url)
        app.state.sessionmaker = build_sessionmaker(app.state.engine)
        try:
            yield
        finally:
            await app.state.llm_client.aclose()
            await app.state.retriever.embedder.aclose()
            await app.state.engine.dispose()

    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(search.router)
    app.include_router(documents.router)
    return app


app = create_app()
