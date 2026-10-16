"""Direct, city-scoped Open-Meteo forecasts without Hugging Face."""

import os
import re
import math
import logging
from datetime import datetime, timezone, timedelta
from collections.abc import Callable

import httpx


logger = logging.getLogger(__name__)
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_CODES = {
    0: "晴",
    1: "大部晴朗",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "冻雾",
    51: "小毛毛雨",
    53: "中等毛毛雨",
    55: "强毛毛雨",
    56: "轻冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "轻冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "中等阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴大冰雹",
}


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _condition(value: object) -> str:
    code = _number(value)
    return WEATHER_CODES.get(int(code), "未知") if code is not None and code.is_integer() else "未知"


def _place_label(place: dict[str, object]) -> dict[str, object]:
    return {"name": place["name"], "region": place.get("admin1", ""), "country": place.get("country", "")}


class WeatherClient:
    """Resolve cities and retrieve bounded current and daily forecasts."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Configure HTTP and clock dependencies for freshness checks."""
        self.transport = transport
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def _locations(self, client: httpx.AsyncClient, city: str, region: str) -> list[dict[str, object]]:
        query = f"{city}, {region}" if region else city
        response = await client.get(GEOCODING_URL, params={"name": query, "count": 5, "language": "zh"})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("results", []), list):
            raise ValueError("invalid_geocoding_response")
        places = []
        for entry in payload.get("results", []):
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                continue
            latitude, longitude = _number(entry.get("latitude")), _number(entry.get("longitude"))
            if latitude is None or longitude is None or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                continue
            places.append({str(key): value for key, value in entry.items()})
        return places

    async def forecast(
        self,
        *,
        city: str = "",
        region: str = "",
        day_offset: int = 0,
    ) -> dict[str, object]:
        """Return one city's forecast, or ask for a missing/ambiguous location."""
        if type(day_offset) is not int or not 0 <= day_offset <= 6:
            raise ValueError("day_offset must be an integer from 0 to 6")
        if not isinstance(city, str) or not isinstance(region, str):
            raise ValueError("city and region must be strings")
        used_default = not city.strip()
        city = (os.getenv("WEATHER_DEFAULT_CITY", "") if used_default else city).strip()
        region = (os.getenv("WEATHER_DEFAULT_REGION", "") if used_default and not region.strip() else region).strip()
        if not city:
            return {
                "status": "needs_location",
                "message": "Ask which city the user wants; no default city is configured.",
            }
        municipality = city.removesuffix("市").lower()
        if (
            municipality in {"北京", "上海", "天津", "重庆", "beijing", "shanghai", "tianjin", "chongqing"}
            and municipality == region.removesuffix("市").lower()
        ):
            region = ""
        if len(city) > 100 or len(region) > 100 or re.search(r"[\x00-\x1f\x7f]", city + region):
            raise ValueError("invalid_location")
        try:
            async with httpx.AsyncClient(
                timeout=8, trust_env=False, follow_redirects=False, transport=self.transport
            ) as client:
                places = await self._locations(client, city, region)
                administrative = [p for p in places if str(p.get("feature_code", "")).startswith(("PPLA", "PPLC"))]
                if not administrative and re.fullmatch(r"[\u4e00-\u9fff]{2,12}", city):
                    alternate = city[:-1] if city.endswith("市") else city + "市"
                    alternatives = await self._locations(client, alternate, region)
                    administrative = [
                        p for p in alternatives if str(p.get("feature_code", "")).startswith(("PPLA", "PPLC"))
                    ]
                    places = places or alternatives
                places = administrative or places
                if not places:
                    return {
                        "status": "location_not_found",
                        "message": "Ask for the city and province/country, or its English name.",
                    }
                if len(places) > 1:
                    return {
                        "status": "needs_clarification",
                        "locations": [_place_label(p) for p in places],
                        "message": "Ask the user to choose a province/country; do not pick a location silently.",
                    }
                place = places[0]
                response = await client.get(
                    FORECAST_URL,
                    params={
                        "latitude": str(place["latitude"]),
                        "longitude": str(place["longitude"]),
                        "timezone": str(place.get("timezone", "auto")),
                        "forecast_days": 7,
                        "temperature_unit": "celsius",
                        "wind_speed_unit": "kmh",
                        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
                        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("invalid_forecast")
                current, daily = payload.get("current"), payload.get("daily")
                if not isinstance(current, dict) or not isinstance(daily, dict):
                    raise ValueError("invalid_forecast")
                dates = daily.get("time")
                if not isinstance(dates, list) or len(dates) <= day_offset or not isinstance(dates[day_offset], str):
                    raise ValueError("invalid_forecast_dates")
                now = self.clock()
                offset = _number(payload.get("utc_offset_seconds"))
                if offset is None or not -50400 <= offset <= 50400:
                    raise ValueError("invalid_weather_timezone")
                local_timezone = timezone(timedelta(seconds=offset))
                expected_day = now.astimezone(local_timezone).date() + timedelta(days=day_offset)
                if datetime.fromisoformat(dates[day_offset]).date() != expected_day:
                    raise ValueError("stale_forecast_date")
                current_fresh = False
                reference = current.get("time")
                if isinstance(reference, str):
                    try:
                        reference_time = datetime.fromisoformat(reference)
                        if reference_time.tzinfo is None:
                            reference_time = reference_time.replace(tzinfo=local_timezone)
                        current_fresh = -timedelta(minutes=30) <= now - reference_time <= timedelta(hours=3)
                    except ValueError:
                        current_fresh = False
                selected = {}
                for key in (
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                ):
                    values = daily.get(key)
                    selected[key] = (
                        values[day_offset] if isinstance(values, list) and len(values) > day_offset else None
                    )
                return {
                    "provider": "Open-Meteo",
                    "location": _place_label(place),
                    "used_default_location": used_default,
                    "timezone": payload.get("timezone"),
                    "fetched_at": now.isoformat(),
                    "source_url": str(response.url),
                    "notice": "Model-based weather data, not a local sensor. Say the city, forecast date and reference time. Null means unavailable; never invent measurements.",
                    "current_status": "available" if current_fresh else "stale_or_missing",
                    "current": {
                        "reference_time": current.get("time"),
                        "temperature_c": _number(current.get("temperature_2m")),
                        "apparent_temperature_c": _number(current.get("apparent_temperature")),
                        "humidity_percent": _number(current.get("relative_humidity_2m")),
                        "condition": _condition(current.get("weather_code")),
                        "wind_kmh": _number(current.get("wind_speed_10m")),
                    }
                    if current_fresh
                    else None,
                    "forecast": {
                        "date": dates[day_offset],
                        "condition": _condition(selected["weather_code"]),
                        "high_c": _number(selected["temperature_2m_max"]),
                        "low_c": _number(selected["temperature_2m_min"]),
                        "rain_probability_percent": _number(selected["precipitation_probability_max"]),
                    },
                }
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Weather lookup failed: %s", type(exc).__name__)
            return {"error": "Weather service is temporarily unavailable. Do not invent weather data."}
