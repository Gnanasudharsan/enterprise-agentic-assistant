"""The backend's side of MCP: a typed gateway to tool servers.

Agents and routes depend on `ToolGateway`, so tests can swap in a stub. The real gateway
spawns the tracker MCP server as a subprocess with an explicit, minimal environment: the
server gets the tracker credentials, and nothing else (no model key, no database URL).
"""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from opentelemetry import trace

from app.core.config import Settings

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("app.actions")

BACKEND_DIR = Path(__file__).resolve().parents[2]
CALL_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only_hint: bool  # what the server claims; the backend's policy decides


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None


class ToolGateway(Protocol):
    server: str
    tools: list[ToolSpec]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult: ...


class MCPGateway:
    def __init__(self, client: Client, server: str, tools: list[ToolSpec]) -> None:
        self._client = client
        self.server = server
        self.tools = tools

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        with tracer.start_as_current_span(
            f"mcp.call_tool {name}",
            kind=trace.SpanKind.CLIENT,
            attributes={"mcp.server": self.server, "mcp.tool": name},
        ) as span:
            result = await self._call(name, arguments)
            span.set_attribute("mcp.ok", result.ok)
            return result

    async def _call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            result = await self._client.call_tool(
                name, arguments, read_timeout_seconds=CALL_TIMEOUT_SECONDS
            )
        except Exception as exc:  # noqa: BLE001 - transport and protocol errors
            logger.warning("MCP call %s failed: %s", name, exc)
            return ToolResult(ok=False, error=f"The tool server failed ({type(exc).__name__}).")
        if getattr(result, "is_error", False):
            text = " ".join(getattr(c, "text", "") for c in result.content).strip()
            return ToolResult(ok=False, error=text[:500] or "The tool returned an error.")
        return ToolResult(ok=True, data=getattr(result, "structured_content", None) or {})


def tracker_server_params(settings: Settings) -> StdioServerParameters:
    db_path = Path(settings.tracker_db_path)
    env = {
        "TRACKER_BACKEND": settings.tracker_backend,
        "TRACKER_DB_PATH": str(db_path if db_path.is_absolute() else BACKEND_DIR / db_path),
    }
    if settings.tracker_backend == "github":
        assert settings.github_repo and settings.github_token  # checked by Settings
        env["GITHUB_REPO"] = settings.github_repo
        env["GITHUB_TOKEN"] = settings.github_token.get_secret_value()
    return StdioServerParameters(
        command=sys.executable, args=["-m", "app.mcp_servers.tracker"], env=env, cwd=BACKEND_DIR
    )


async def load_tools(client: Client) -> list[ToolSpec]:
    listed = await client.list_tools()
    return [
        ToolSpec(
            name=t.name,
            description=t.description or "",
            input_schema=t.input_schema,
            read_only_hint=bool(t.annotations and t.annotations.read_only_hint),
        )
        for t in listed.tools
    ]


@asynccontextmanager
async def open_tracker_gateway(settings: Settings) -> AsyncIterator[ToolGateway | None]:
    """Connect to the tracker MCP server. Yields None (actions off) if it can't start."""
    if not settings.actions_enabled:
        yield None
        return
    try:
        client = Client(tracker_server_params(settings))
        await client.__aenter__()
        tools = await load_tools(client)
    except Exception as exc:  # noqa: BLE001 - the assistant still works without actions
        logger.error("Tracker MCP server unavailable, actions disabled: %s", exc)
        yield None
        return
    try:
        yield MCPGateway(client, f"tracker-{settings.tracker_backend}", tools)
    finally:
        await client.__aexit__(None, None, None)
