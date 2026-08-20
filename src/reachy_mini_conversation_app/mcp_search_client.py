"""Minimal Streamable HTTP MCP client for bounded web-search tool calls."""

import os
import json
from typing import Any
from urllib.parse import urlsplit

import httpx


DEFAULT_MCP_SEARCH_URL = "https://mcp.exa.ai/mcp"
DEFAULT_MCP_SEARCH_TOOL = "web_search_exa"
MCP_PROTOCOL_VERSION = "2025-03-26"


class McpSearchError(RuntimeError):
    """Raised when the remote MCP search operation cannot be completed."""


class McpSearchClient:
    """Call one remote MCP search tool through a short-lived HTTP session."""

    def __init__(
        self,
        *,
        url: str | None = None,
        tool_name: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        max_content_chars: int = 6000,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize configuration for one bounded remote MCP endpoint."""
        self.url = (url or os.getenv("MCP_WEB_SEARCH_URL") or DEFAULT_MCP_SEARCH_URL).strip()
        self.tool_name = (tool_name or os.getenv("MCP_WEB_SEARCH_TOOL") or DEFAULT_MCP_SEARCH_TOOL).strip()
        self.api_key = api_key if api_key is not None else os.getenv("EXA_API_KEY")
        configured_timeout = timeout_seconds
        if configured_timeout is None:
            try:
                configured_timeout = float(os.getenv("MCP_WEB_SEARCH_TIMEOUT_SECONDS", "8"))
            except ValueError:
                configured_timeout = 8.0
        self.timeout_seconds = min(30.0, max(2.0, configured_timeout))
        self.max_content_chars = max(1, max_content_chars)
        self.transport = transport
        self._validate_url()

    def _validate_url(self) -> None:
        parts = urlsplit(self.url)
        if (
            parts.scheme.lower() != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
        ):
            raise ValueError("MCP web search endpoint must be an HTTPS URL without embedded credentials")

    @staticmethod
    def _decode_response(response: httpx.Response, *, request_id: int) -> dict[str, Any]:
        if not response.is_success:
            raise McpSearchError(f"MCP server returned HTTP {response.status_code}")
        if not response.content:
            return {}

        content_type = response.headers.get("content-type", "").lower()
        payloads: list[dict[str, Any]] = []
        if "text/event-stream" in content_type:
            for line in response.text.splitlines():
                if not line.startswith("data:"):
                    continue
                try:
                    value = json.loads(line[5:].strip())
                except json.JSONDecodeError as exc:
                    raise McpSearchError("MCP server returned invalid SSE JSON") from exc
                if isinstance(value, dict):
                    payloads.append(value)
        else:
            try:
                value = response.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise McpSearchError("MCP server returned invalid JSON") from exc
            if isinstance(value, dict):
                payloads.append(value)

        for payload in payloads:
            if payload.get("id") != request_id:
                continue
            if "error" in payload:
                error = payload.get("error")
                message = error.get("message") if isinstance(error, dict) else None
                raise McpSearchError(str(message or "MCP request failed"))
            result = payload.get("result")
            if isinstance(result, dict):
                return result
        raise McpSearchError("MCP server did not return the requested response")

    async def _search_once(self, query: str, num_results: int) -> dict[str, object]:
        headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key

        session_id: str | None = None
        async with httpx.AsyncClient(
            headers=headers,
            timeout=self.timeout_seconds,
            follow_redirects=True,
            trust_env=False,
            transport=self.transport,
        ) as client:
            try:
                initialize = await client.post(
                    self.url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": MCP_PROTOCOL_VERSION,
                            "capabilities": {},
                            "clientInfo": {"name": "reachy-mini-qwen-realtime", "version": "1.0.1"},
                        },
                    },
                )
                self._decode_response(initialize, request_id=1)
                session_id = initialize.headers.get("mcp-session-id")
                if not session_id:
                    raise McpSearchError("MCP server did not provide a session identifier")

                session_headers = {"mcp-session-id": session_id}
                initialized = await client.post(
                    self.url,
                    headers=session_headers,
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                )
                if not initialized.is_success:
                    raise McpSearchError(f"MCP initialization notification returned HTTP {initialized.status_code}")

                response = await client.post(
                    self.url,
                    headers=session_headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": self.tool_name,
                            "arguments": {"query": query, "numResults": num_results},
                        },
                    },
                )
                result = self._decode_response(response, request_id=2)
                blocks = result.get("content")
                text_blocks = (
                    [
                        str(block.get("text"))
                        for block in blocks
                        if isinstance(block, dict) and block.get("type") == "text"
                    ]
                    if isinstance(blocks, list)
                    else []
                )
                content = "\n\n".join(text_blocks).strip()
                if not content:
                    raise McpSearchError("MCP search returned no text content")
                return {
                    "provider": "exa-mcp",
                    "content": content[: self.max_content_chars],
                }
            except httpx.HTTPError as exc:
                raise McpSearchError("MCP web search network request failed") from exc
            finally:
                if session_id:
                    try:
                        await client.delete(self.url, headers={"mcp-session-id": session_id})
                    except httpx.HTTPError:
                        pass

    async def search(self, query: str, *, num_results: int = 5) -> dict[str, object]:
        """Search the web through the configured MCP server."""
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must be a non-empty string")
        bounded_results = min(5, max(1, int(num_results)))
        last_error: McpSearchError | None = None
        for _attempt in range(2):
            try:
                return await self._search_once(normalized_query, bounded_results)
            except McpSearchError as exc:
                last_error = exc
        raise last_error or McpSearchError("MCP web search failed")
