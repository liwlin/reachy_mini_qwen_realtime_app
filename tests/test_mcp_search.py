"""Tests for the optional Streamable HTTP MCP web-search integration."""

from __future__ import annotations
import json
import importlib
import importlib.util
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from reachy_mini_conversation_app.tools.core_tools import ToolDependencies


def _search_types() -> tuple[type[Any], type[Exception], type[Any]]:
    """Load the optional search types after proving both modules exist."""
    assert importlib.util.find_spec("reachy_mini_conversation_app.mcp_search_client") is not None
    assert importlib.util.find_spec("reachy_mini_conversation_app.tools.web_search") is not None
    client_module = importlib.import_module("reachy_mini_conversation_app.mcp_search_client")
    tool_module = importlib.import_module("reachy_mini_conversation_app.tools.web_search")
    return client_module.McpSearchClient, client_module.McpSearchError, tool_module.WebSearch


def _sse(payload: dict[str, Any]) -> str:
    return f"event: message\ndata: {json.dumps(payload)}\n\n"


@pytest.mark.asyncio
async def test_mcp_search_initializes_calls_tool_and_closes_session() -> None:
    """The client should negotiate, call Exa, and close the MCP session."""
    McpSearchClient, _, _ = _search_types()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)

        payload = json.loads(request.content or b"{}")
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream", "mcp-session-id": "session-test"},
                text=_sse(
                    {
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "result": {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "exa-search-server", "version": "test"},
                        },
                    }
                ),
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/call":
            assert payload["params"] == {
                "name": "web_search_exa",
                "arguments": {"query": "latest Reachy Mini news", "numResults": 3},
            }
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=_sse(
                    {
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Title: Reachy Mini\nURL: https://example.test/reachy\nHighlights: Current result.",
                                }
                            ]
                        },
                    }
                ),
            )
        raise AssertionError(f"Unexpected request: {request.method} {method}")

    client = McpSearchClient(
        url="https://mcp.exa.ai/mcp",
        api_key="exa-secret-test",
        transport=httpx.MockTransport(handler),
    )

    result = await client.search("latest Reachy Mini news", num_results=3)

    assert result["provider"] == "exa-mcp"
    assert "https://example.test/reachy" in result["content"]
    assert "exa-secret-test" not in json.dumps(result)
    assert [request.method for request in requests] == ["POST", "POST", "POST", "DELETE"]
    assert requests[0].headers["x-api-key"] == "exa-secret-test"
    assert requests[2].headers["mcp-session-id"] == "session-test"


@pytest.mark.asyncio
async def test_mcp_search_truncates_untrusted_result_content() -> None:
    """Remote text must stay within the configured Qwen context budget."""
    McpSearchClient, _, _ = _search_types()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(204)
        payload = json.loads(request.content or b"{}")
        if payload.get("method") == "initialize":
            return httpx.Response(
                200,
                headers={"content-type": "application/json", "mcp-session-id": "session-test"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "test", "version": "1"},
                    },
                },
            )
        if payload.get("method") == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"content": [{"type": "text", "text": "x" * 7000}]},
            },
        )

    client = McpSearchClient(transport=httpx.MockTransport(handler), max_content_chars=6000)
    result = await client.search("query")

    assert len(result["content"]) == 6000


@pytest.mark.asyncio
async def test_mcp_search_rejects_empty_query_and_non_https_endpoint() -> None:
    """Invalid local input must fail before any outbound request."""
    McpSearchClient, _, _ = _search_types()
    with pytest.raises(ValueError, match="query"):
        await McpSearchClient().search("  ")

    with pytest.raises(ValueError, match="HTTPS"):
        McpSearchClient(url="http://127.0.0.1:8766/mcp")


@pytest.mark.asyncio
async def test_web_search_tool_isolates_mcp_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Search failures should return a tool error without crashing conversation."""
    McpSearchClient, McpSearchError, WebSearch = _search_types()
    search = AsyncMock(side_effect=McpSearchError("remote search unavailable"))
    monkeypatch.setattr(McpSearchClient, "search", search)
    deps = ToolDependencies(reachy_mini=object(), movement_manager=object())  # type: ignore[arg-type]

    result = await WebSearch()(deps, query="today's robotics news", num_results=2)

    assert result == {"error": "Web search is temporarily unavailable."}
    search.assert_awaited_once_with("today's robotics news", num_results=2)
