"""Tests for the optional Streamable HTTP MCP web-search integration."""

from __future__ import annotations
import json
import importlib
import importlib.util
from typing import Any
from datetime import datetime, timezone, timedelta
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
            assert payload["params"]["name"] == "web_search_exa"
            arguments = payload["params"]["arguments"]
            assert arguments["query"] == "latest Reachy Mini news"
            assert arguments["numResults"] == 3
            assert isinstance(arguments.get("objective"), str) and arguments["objective"].strip()
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


def _mcp_transport(tool_result, requests):
    def handler(request):
        requests.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        payload = json.loads(request.content)
        if payload.get("method") == "initialize":
            return httpx.Response(
                200,
                headers={"mcp-session-id": "news-test"},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "serverInfo": {"name": "test", "version": "1"},
                    },
                },
            )
        if payload.get("method") == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 2, "result": tool_result})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_mcp_tool_error_is_not_presented_as_search_evidence():
    """An MCP error response must not become purported search evidence."""
    Client, Error, _ = _search_types()
    requests = []
    client = Client(
        transport=_mcp_transport(
            {"isError": True, "content": [{"type": "text", "text": "private upstream failure"}]},
            requests,
        )
    )
    with pytest.raises(Error) as captured:
        await client.search("latest news")
    assert "private upstream failure" not in str(captured.value)


@pytest.mark.asyncio
async def test_news_filters_stale_future_undated_and_duplicate_sources():
    """Only dated, recent, unique public links survive the news boundary."""
    Client, _, _ = _search_types()
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(hours=2)).isoformat()
    entries = [
        {
            "url": "https://news.example/story",
            "title": "A real update",
            "publishedDate": recent,
            "text": "evidence " * 2000,
        },
        {"url": "https://news.example/story", "title": "Duplicate", "publishedDate": recent},
        {"url": "https://news.example/old", "title": "Old", "publishedDate": (now - timedelta(days=10)).isoformat()},
        {"url": "https://news.example/future", "publishedDate": (now + timedelta(days=1)).isoformat()},
        {"url": "https://news.example/unknown", "title": "Undated"},
        {"url": "javascript:alert(1)", "title": "Unsafe link", "publishedDate": recent},
    ]
    requests = []
    client = Client(
        transport=_mcp_transport(
            {"content": [{"type": "text", "text": json.dumps({"results": entries})}]},
            requests,
        )
    )
    result = await client.search_news("科技新闻", days=2, num_results=3)
    assert len(result["results"]) == 1
    assert result["results"][0]["url"] == "https://news.example/story"
    assert result["results"][0]["published_at"] == recent
    assert len(result["results"][0]["excerpt"]) <= 1000
    assert result["status"] == "ok"
    call = next(
        json.loads(r.content)
        for r in requests
        if r.method == "POST" and json.loads(r.content).get("method") == "tools/call"
    )
    assert call["params"]["name"] == "web_search_advanced_exa"
    arguments = call["params"]["arguments"]
    assert arguments["category"] == "news"
    assert arguments["numResults"] == 3
    start = datetime.fromisoformat(arguments["startPublishedDate"])
    end = datetime.fromisoformat(arguments["endPublishedDate"])
    assert end - start == timedelta(days=2)
    assert start < datetime.fromisoformat(recent) < end
    assert "web_search_advanced_exa" in requests[0].url.params["tools"]


@pytest.mark.asyncio
async def test_news_returns_no_results_without_inventing_headlines():
    """An empty provider result stays empty for the model."""
    Client, _, _ = _search_types()
    client = Client(
        transport=_mcp_transport(
            {"content": [{"type": "text", "text": json.dumps({"results": []})}]},
            [],
        )
    )
    result = await client.search_news("rare event", days=1)
    assert result["status"] == "no_recent_results"
    assert result["results"] == []


@pytest.mark.asyncio
async def test_news_rejects_invalid_windows_before_network():
    """Invalid news windows are rejected without external requests."""
    Client, _, _ = _search_types()
    requests = []
    client = Client(transport=_mcp_transport({}, requests))
    for days in (0, 8, True, "1"):
        with pytest.raises(ValueError):
            await client.search_news("news", days=days)
    assert not requests


@pytest.mark.asyncio
async def test_plain_text_news_failure_becomes_a_bounded_tool_error(monkeypatch):
    """Malformed provider text never becomes a headline or crashes the robot tool."""
    from reachy_mini_conversation_app.tools import get_news

    Client, _, _ = _search_types()
    client = Client(
        transport=_mcp_transport(
            {"content": [{"type": "text", "text": "private provider debug text"}]},
            [],
        )
    )
    monkeypatch.setattr(get_news, "McpSearchClient", lambda: client)
    deps = ToolDependencies(reachy_mini=object(), movement_manager=object())
    result = await get_news.GetNews()(deps, query="news")
    assert result == {"error": "News search is temporarily unavailable. Do not invent headlines."}
