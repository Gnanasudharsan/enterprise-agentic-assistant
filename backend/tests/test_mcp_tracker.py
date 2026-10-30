"""The tracker MCP server through the real MCP client and the backend's gateway."""

from contextlib import asynccontextmanager

from mcp import Client

from app.actions.gateway import MCPGateway, load_tools, tracker_server_params
from app.core.config import Settings
from app.mcp_servers.tracker import LocalTracker, build_server


@asynccontextmanager
async def connect(tmp_path):
    # Opened inside each test: the client's task group must start and end in one task.
    async with Client(build_server(LocalTracker(str(tmp_path / "t.sqlite3")))) as client:
        yield MCPGateway(client, "tracker-local", await load_tools(client))


async def test_tools_are_typed_and_annotated(tmp_path):
    async with connect(tmp_path) as gateway:
        tools = {t.name: t for t in gateway.tools}
    tools = {t.name: t for t in gateway.tools}
    assert set(tools) == {"create_issue", "search_issues"}
    schema = tools["create_issue"].input_schema
    assert schema["required"] == ["title", "body"]
    assert schema["properties"]["priority"]["enum"] == ["P1", "P2", "P3", "P4"]
    assert tools["search_issues"].read_only_hint and not tools["create_issue"].read_only_hint


async def test_create_then_search(tmp_path):
    async with connect(tmp_path) as gateway:
        created, found = await create_and_search(gateway)
    assert created.ok and created.data["key"] == "HEL-1"
    assert created.data["labels"] == ["verification", "priority:P2"]
    assert [i["key"] for i in found.data["issues"]] == ["HEL-1"]


async def create_and_search(gateway):
    created = await gateway.call("create_issue", {
        "title": "Add bulk retry for KYB checks", "body": "Context: INC-204 follow-up item.",
        "labels": ["verification"], "priority": "P2"})  # fmt: skip
    return created, await gateway.call("search_issues", {"query": "bulk retry KYB"})


async def test_server_rejects_invalid_arguments(tmp_path):
    async with connect(tmp_path) as gateway:
        result = await gateway.call("create_issue", {"title": "short", "body": "too short"})
    assert not result.ok and "validation error" in result.error


def test_subprocess_gets_only_tracker_settings(tmp_path):
    settings = Settings(
        _env_file=None, llm_api_key="sk-test-not-real", tracker_db_path=str(tmp_path / "t.db")
    )
    params = tracker_server_params(settings)
    assert set(params.env) == {"TRACKER_BACKEND", "TRACKER_DB_PATH"}
    assert "sk-test-not-real" not in str(params)


async def test_search_needs_a_real_overlap(tmp_path):
    async with connect(tmp_path) as gateway:
        await create_and_search(gateway)
        unrelated = await gateway.call(
            "search_issues", {"query": "alert when kyb-verification tickets exceed 10 in 48 hours"}
        )
    assert unrelated.data["issues"] == []
