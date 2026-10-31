"""Graph construction and the checkpointer."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy
from sqlalchemy.exc import OperationalError

from app.agents.action_nodes import ActionAgents
from app.agents.nodes import AgentDeps, Agents
from app.agents.state import AgentState
from app.core.config import Settings
from app.core.telemetry import traced_node
from app.llm.base import LLMError

# Transient infrastructure failures are retried with backoff. Logical failures (bad
# plans, bad SQL) are handled inside the nodes, which repair or fall back instead.
DB_RETRY = RetryPolicy(max_attempts=3, initial_interval=0.5, retry_on=(OperationalError, OSError))
LLM_RETRY = RetryPolicy(max_attempts=2, initial_interval=1.0, retry_on=LLMError)


def build_graph(deps: AgentDeps, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    agents = Agents(deps)
    actions = ActionAgents(deps)
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", traced_node("supervisor", agents.supervisor))
    graph.add_node("research", traced_node("research", agents.research), retry_policy=DB_RETRY)
    graph.add_node("data", traced_node("data", agents.data), retry_policy=DB_RETRY)
    graph.add_node("coordinator", traced_node("coordinator", agents.coordinator))
    graph.add_node("analyst", traced_node("analyst", agents.analyst), retry_policy=LLM_RETRY)
    graph.add_node(
        "propose_action",
        traced_node("propose_action", actions.propose_action),
        retry_policy=DB_RETRY,
    )
    graph.add_node("approval", traced_node("approval", actions.approval))
    graph.add_node("execute_action", traced_node("execute_action", actions.execute_action))

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", agents.route, ["research", "data", "analyst"])
    # Each wave of steps joins at the coordinator, which dispatches dependent steps (with
    # their dependencies' findings) or, when every step is done, the analyst.
    graph.add_edge("research", "coordinator")
    graph.add_edge("data", "coordinator")
    graph.add_conditional_edges("coordinator", agents.route, ["research", "data", "analyst"])
    # Actions: draft after the answer, stop for a human decision, then execute (or not).
    graph.add_conditional_edges("analyst", actions.after_analyst, ["propose_action", END])
    graph.add_conditional_edges("propose_action", actions.after_proposal, ["approval", END])
    graph.add_edge("approval", "execute_action")
    graph.add_edge("execute_action", END)
    return graph.compile(checkpointer=checkpointer, name="enterprise-assistant")


@asynccontextmanager
async def open_checkpointer(settings: Settings) -> AsyncIterator[BaseCheckpointSaver]:
    """Postgres checkpoints survive restarts, so interrupted runs can be resumed."""
    if settings.agent_checkpointer == "memory" or not settings.sqlalchemy_url.startswith(
        "postgresql"
    ):
        yield InMemorySaver()
        return

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    pool = AsyncConnectionPool(
        conninfo=settings.psycopg_url,
        max_size=settings.db_pool_size,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open()
    try:
        saver = AsyncPostgresSaver(pool)
        await saver.setup()  # creates/migrates the checkpoint tables; idempotent
        yield saver
    finally:
        await pool.close()
