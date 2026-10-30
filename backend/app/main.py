"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.actions.gateway import open_tracker_gateway
from app.actions.policy import ActionPolicy
from app.agents.graph import build_graph, open_checkpointer
from app.agents.nodes import AgentDeps
from app.agents.service import AgentService
from app.analytics.sql import SQLExecutor
from app.api.routes import agent, chat, documents, health, search
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
        if getattr(app.state, "sql_executor", None) is None:
            app.state.sql_executor = SQLExecutor(
                app.state.engine, timeout_ms=settings.sql_timeout_ms, max_rows=settings.sql_max_rows
            )
        async with AsyncExitStack() as stack:
            checkpointer = await stack.enter_async_context(open_checkpointer(settings))
            # Tests may pre-populate app.state.tool_gateway with a stub.
            if not hasattr(app.state, "tool_gateway"):
                app.state.tool_gateway = await stack.enter_async_context(
                    open_tracker_gateway(settings)
                )
            deps = AgentDeps(
                llm=app.state.llm_client,
                retriever=app.state.retriever,
                sessionmaker=app.state.sessionmaker,
                sql=app.state.sql_executor,
                settings=settings,
                tools=app.state.tool_gateway,
            )
            app.state.agent_service = AgentService(
                build_graph(deps, checkpointer),
                app.state.sessionmaker,
                app.state.llm_client,
                policy=ActionPolicy.from_settings(settings.action_permissions),
                tools=app.state.tool_gateway,
                user_id=settings.user_id,
            )
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
    app.include_router(agent.router)
    app.include_router(agent.actions_router)
    return app


app = create_app()
