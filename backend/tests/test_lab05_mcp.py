"""Lab 5 — MCP connector: a real MCP server spoken to over a real MCP client.

These tests spawn the stdio server as a subprocess and drive it with the official
SDK, so they prove protocol compliance rather than a bespoke function registry.
They deliberately use only offline tools; the live-network variants are marked.
"""

from __future__ import annotations

import pytest

from app.mcp.client import McpClient, probe_server
from app.tools.registry import get_registry
from app.tools.runner import ToolRunner


@pytest.mark.asyncio
@pytest.mark.slow
async def test_mcp_server_discovery_and_initialize(project):
    probe = await probe_server()
    assert probe["ok"] is True, probe.get("error")
    assert probe["protocol"] == "mcp"
    assert probe["transport"] == "stdio"
    assert probe["tool_count"] >= 14
    assert "search_openalex" in probe["tools"]
    assert probe["server"]["name"] == "agentic-research-tools"
    assert probe["server"]["protocol_version"]


@pytest.mark.asyncio
@pytest.mark.slow
async def test_mcp_tool_executes_through_protocol(project):
    client = McpClient()
    try:
        tools = await client.list_tools()
        schema = next(t for t in tools if t["name"] == "compare_papers")["input_schema"]
        assert "papers" in schema["properties"]

        result = await client.call_tool(
            "compare_papers",
            {
                "topic": "road anomaly detection",
                "papers": [
                    {
                        "id": "x1",
                        "title": "YOLO road anomaly detection",
                        "abstract": "We propose YOLO. A limitation is cross-city generalisation.",
                        "year": 2024,
                        "sources": ["crossref"],
                    }
                ],
            },
        )
        assert result["count"] == 1
        assert result["rows"][0]["title"] == "YOLO road anomaly detection"
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.slow
async def test_mcp_path_traversal_is_rejected_inside_the_server(project):
    client = McpClient()
    try:
        res = await client.call_tool("read_research_file", {"rel_path": "../../etc/passwd"})
        assert res["ok"] is False
        assert "path rejected" in res["error"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.slow
async def test_runner_uses_mcp_transport_and_records_it(project):
    runner = ToolRunner(project_id=project.id, run_id=None, transport="mcp")
    await runner.start()
    try:
        assert runner.mode == "mcp", runner.transport_note
        assert "mcp" in runner.transport_note.lower()
        res = await runner.call(
            "compare_papers",
            {"topic": "road anomaly", "papers": [{"id": "1", "title": "T", "abstract": "a", "sources": ["x"]}]},
        )
        assert res["count"] == 1
        assert runner.invocations[-1]["transport"] == "mcp"
    finally:
        await runner.aclose()


@pytest.mark.asyncio
async def test_registry_and_mcp_expose_the_same_tools():
    registry_tools = set(get_registry().names())
    probe = await probe_server()
    assert registry_tools == set(probe["tools"])
