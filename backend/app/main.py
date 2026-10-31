"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import __version__
from app.actions.gateway import open_tracker_gateway
from app.actions.policy import ActionPolicy
from app.agents.graph import build_graph, open_checkpointer
from app.agents.nodes import AgentDeps
from app.agents.service import AgentService
from app.analytics.sql import SQLExecutor
from app.api.routes import access, agent, chat, documents, health, search
from app.core.config import Settings, get_settings
from app.core.logs import install_access_log, setup_logging
from app.core.protection import install_protection
from app.core.telemetry import setup_tracing
from app.db.session import build_engine, build_sessionmaker
from app.llm.budget import BudgetedLLM, DailyBudget
from app.llm.factory import build_llm_client
from app.llm.fake import FakeLLMClient
from app.llm.metering import MeteredLLM
from app.rag.factory import build_embedder, build_retriever


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Tests may pre-populate app.state.llm_client / retriever with stubs.
        if getattr(app.state, "llm_client", None) is None:
            app.state.llm_client = build_llm_client(settings)
            if settings.daily_token_budget and app.state.llm_client.provider != "fake":
                # Past the day's budget, answers come from the offline model at no cost.
                app.state.budget = DailyBudget(settings.daily_token_budget)
                app.state.llm_client = BudgetedLLM(
                    app.state.llm_client, FakeLLMClient(), app.state.budget
                )
        # Count tokens per request (cost) and trace every model call, stubs included.
        if not isinstance(app.state.llm_client, MeteredLLM):
            app.state.llm_client = MeteredLLM(app.state.llm_client)
        if getattr(app.state, "retriever", None) is None:
            embedder = build_embedder(settings)
            app.state.retriever = build_retriever(settings, embedder, app.state.llm_client)
        app.state.engine = build_engine(settings.sqlalchemy_url, settings.db_pool_size)
        app.state.sessionmaker = build_sessionmaker(app.state.engine)
        if budget := getattr(app.state, "budget", None):
            await budget.load(app.state.sessionmaker)
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
    setup_tracing(app, settings)

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
    app.include_router(access.router)
    install_access_log(app)
    install_protection(app, settings)  # outermost: runs before the routes and the log
    if settings.static_dir:
        mount_frontend(app, Path(settings.static_dir))
    return app


def mount_frontend(app: FastAPI, root: Path) -> None:
    """Serve the built single-page app: files as they are, every other path as index.html
    (client-side routes). Registered last, so API routes always win."""
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"STATIC_DIR has no index.html: {root}")
    root = root.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str) -> FileResponse:
        if path.startswith(("api/", "health")):
            raise HTTPException(404)
        file = (root / path).resolve()
        if path and file.is_file() and file.is_relative_to(root):
            # Vite fingerprints asset names, so they can be cached for good.
            cache = (
                "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            )
            return FileResponse(file, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
