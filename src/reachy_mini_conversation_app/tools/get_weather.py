"""City weather tool for Qwen and the shared function registry."""

from typing import Any

from reachy_mini_conversation_app.weather_client import WeatherClient
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


class GetWeather(Tool):
    """Read structured weather without an HF-hosted tool."""

    name = "get_weather"
    description = (
        "Look up current weather and a daily forecast. Always call this for weather, temperature or rain questions. "
        "If the user gives a city, use it; otherwise OMIT city and region to use the configured default. "
        "Split province/country into region (city='江门市', region='广东'). "
        "Respect clarification/error results. Say the returned city, date and source; never guess weather."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "Explicitly requested city only; omit for the default city."},
            "region": {
                "type": "string",
                "description": "Province or country to disambiguate an explicitly named city.",
            },
            "day_offset": {
                "type": "integer",
                "minimum": 0,
                "maximum": 6,
                "description": "0=today, 1=tomorrow, 2=day after tomorrow; measured in the city's local timezone.",
            },
        },
        "required": [],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Return weather evidence or a recoverable validation error."""
        try:
            return await WeatherClient().forecast(
                city=kwargs.get("city", ""),
                region=kwargs.get("region", ""),
                day_offset=kwargs.get("day_offset", 0),
            )
        except ValueError:
            return {"error": "Supply a city/region string and day_offset integer from 0 to 6."}
