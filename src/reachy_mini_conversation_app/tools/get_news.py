"""Recent news through the existing Exa MCP connection."""

import logging
from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.mcp_search_client import McpSearchError, McpSearchClient


logger = logging.getLogger(__name__)


class GetNews(Tool):
    """Return dated news items for a topic."""

    name = "get_news"
    description = (
        "Find recent news about a requested topic or place through Exa MCP. Use this for latest news and headlines. "
        "The server supplies the current date; days=1 searches the last 24 hours, days=7 the last week. "
        "Briefly report up to three stories with publisher and publication date; keep URLs in written answers. "
        "If no dated results or an error is returned, say so; do not invent headlines or silently widen the dates."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Topic or location requested, e.g. 中国科技新闻 or 江门本地新闻.",
            },
            "days": {
                "type": "integer",
                "minimum": 1,
                "maximum": 7,
                "description": "Rolling number of days, default 1.",
            },
            "num_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "Maximum stories, default 3.",
            },
        },
        "required": ["query"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Return bounded news evidence without interrupting the conversation."""
        try:
            return await McpSearchClient().search_news(
                kwargs.get("query", ""),
                days=kwargs.get("days", 1),
                num_results=kwargs.get("num_results", 3),
            )
        except ValueError:
            return {"error": "Supply a news query, days from 1 to 7, and num_results from 1 to 5."}
        except McpSearchError as exc:
            logger.warning("News search failed: %s", type(exc).__name__)
            return {"error": "News search is temporarily unavailable. Do not invent headlines."}
