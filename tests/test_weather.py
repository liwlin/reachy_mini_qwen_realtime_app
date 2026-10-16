"""Weather lookups must resolve the intended city and retain forecast metadata."""

import importlib
import importlib.util
from datetime import datetime, timezone

import httpx
import pytest


def weather_client(transport: httpx.MockTransport, at=None):
    """Load the actual client once the implementation exists."""
    assert importlib.util.find_spec("reachy_mini_conversation_app.weather_client") is not None
    module = importlib.import_module("reachy_mini_conversation_app.weather_client")
    return module.WeatherClient(
        transport=transport,
        clock=lambda: at or datetime(2026, 10, 16, 4, 20, tzinfo=timezone.utc),
    )


def location(name="江门市", region="广东", latitude=22.58333, longitude=113.08333, identifier=1806299):
    """Return a geocoder-shaped city fixture."""
    return {
        "id": identifier,
        "name": name,
        "admin1": region,
        "country": "中国",
        "country_code": "CN",
        "feature_code": "PPLA2",
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "Asia/Shanghai",
    }


def forecast_response():
    """Keep missing measurements distinct from a measured zero."""
    return {
        "timezone": "Asia/Shanghai",
        "utc_offset_seconds": 28800,
        "current": {
            "time": "2026-10-16T12:15",
            "temperature_2m": 30,
            "apparent_temperature": None,
            "relative_humidity_2m": 60,
            "weather_code": 3,
            "wind_speed_10m": 12,
        },
        "daily": {
            "time": ["2026-10-16", "2026-10-17"],
            "weather_code": [3, 61],
            "temperature_2m_max": [33, 29],
            "temperature_2m_min": [23, 22],
            "precipitation_probability_max": [0, 80],
        },
    }


@pytest.mark.asyncio
async def test_default_city_and_tomorrow_are_resolved_without_guessing(monkeypatch):
    """The default province selects the intended city and tomorrow uses its local forecast."""
    monkeypatch.setenv("WEATHER_DEFAULT_CITY", "江门市")
    monkeypatch.setenv("WEATHER_DEFAULT_REGION", "广东")
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.host == "geocoding-api.open-meteo.com":
            assert request.url.params["name"] == "江门市, 广东"
            return httpx.Response(200, json={"results": [location()]})
        assert request.url.host == "api.open-meteo.com"
        assert float(request.url.params["latitude"]) == 22.58333
        assert request.url.params["timezone"] == "Asia/Shanghai"
        return httpx.Response(200, json=forecast_response())

    result = await weather_client(httpx.MockTransport(handler)).forecast(day_offset=1)
    assert result["location"]["name"] == "江门市"
    assert result["location"]["region"] == "广东"
    assert result["forecast"]["date"] == "2026-10-17"
    assert result["forecast"]["rain_probability_percent"] == 80
    assert result["forecast"]["condition"] == "小雨"
    assert result["current"]["apparent_temperature_c"] is None
    assert result["timezone"] == "Asia/Shanghai"
    assert result["source_url"].startswith("https://api.open-meteo.com/v1/forecast?")
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_named_city_does_not_inherit_default_region(monkeypatch):
    """An explicit city replaces the configured location without inheriting its province."""
    monkeypatch.setenv("WEATHER_DEFAULT_CITY", "江门市")
    monkeypatch.setenv("WEATHER_DEFAULT_REGION", "广东")

    def handler(request):
        if request.url.host == "geocoding-api.open-meteo.com":
            assert request.url.params["name"] == "北京"
            return httpx.Response(200, json={"results": [location("北京", "北京", 39.9, 116.4, 1816670)]})
        assert float(request.url.params["latitude"]) == 39.9
        return httpx.Response(200, json=forecast_response())

    result = await weather_client(httpx.MockTransport(handler)).forecast(city="北京")
    assert result["location"]["name"] == "北京"
    assert result["used_default_location"] is False


@pytest.mark.asyncio
async def test_ambiguous_place_requires_clarification_not_first_result(monkeypatch):
    """Same-name cities do not silently select an arbitrary first result."""
    monkeypatch.delenv("WEATHER_DEFAULT_CITY", raising=False)
    queries = []

    def handler(request):
        assert request.url.host == "geocoding-api.open-meteo.com"
        queries.append(request.url.params["name"])
        return httpx.Response(
            200,
            json={
                "results": [
                    location("Springfield", "Illinois", 39.8, -89.6, 1),
                    location("Springfield", "Massachusetts", 42.1, -72.6, 2),
                ]
            },
        )

    result = await weather_client(httpx.MockTransport(handler)).forecast(city="Springfield")
    assert result["status"] == "needs_clarification"
    assert len(result["locations"]) == 2
    assert len(queries) == 1


@pytest.mark.asyncio
async def test_chinese_city_suffix_resolves_city_instead_of_namesake_village():
    """Chinese city aliases must not resolve to a village in a different province."""
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.host == "geocoding-api.open-meteo.com":
            if request.url.params["name"] == "江门":
                village = location("江门", "四川", 28.4452, 105.33396, 1806298)
                village["feature_code"] = "PPL"
                return httpx.Response(200, json={"results": [village]})
            assert request.url.params["name"] == "江门市"
            return httpx.Response(200, json={"results": [location()]})
        assert float(request.url.params["latitude"]) == 22.58333
        return httpx.Response(200, json=forecast_response())

    result = await weather_client(httpx.MockTransport(handler)).forecast(city="江门")
    assert result["location"]["region"] == "广东"
    assert len(seen) == 3


@pytest.mark.asyncio
async def test_weather_missing_city_and_invalid_day_make_no_requests(monkeypatch):
    """Missing location and malformed dates fail before network requests."""
    monkeypatch.delenv("WEATHER_DEFAULT_CITY", raising=False)

    def handler(request):
        pytest.fail("Invalid weather arguments must not perform network requests")

    client = weather_client(httpx.MockTransport(handler))
    assert (await client.forecast())["status"] == "needs_location"
    for offset in (-1, 7, True, "1"):
        with pytest.raises(ValueError):
            await client.forecast(city="北京", day_offset=offset)


@pytest.mark.asyncio
async def test_weather_failure_does_not_expose_upstream_text():
    """Provider failures produce a bounded message without upstream details."""

    def handler(request):
        return httpx.Response(503, text="private upstream debug text")

    result = await weather_client(httpx.MockTransport(handler)).forecast(city="北京")
    assert result == {"error": "Weather service is temporarily unavailable. Do not invent weather data."}


@pytest.mark.asyncio
@pytest.mark.parametrize("city,region", [("北京", "北京市"), ("上海", "上海")])
async def test_duplicate_municipality_region_is_normalized(city, region):
    """A municipality is not passed as its own unsupported geocoder qualifier."""

    def handler(request):
        if request.url.host == "geocoding-api.open-meteo.com":
            assert request.url.params["name"] == city
            return httpx.Response(200, json={"results": [location(city, region)]})
        return httpx.Response(200, json=forecast_response())

    result = await weather_client(httpx.MockTransport(handler)).forecast(city=city, region=region)
    assert result["location"]["name"] == city


@pytest.mark.asyncio
async def test_forecast_date_is_checked_in_city_timezone_at_midnight():
    """UTC yesterday must not shift the requested local day back one day."""

    def handler(request):
        if request.url.host == "geocoding-api.open-meteo.com":
            return httpx.Response(200, json={"results": [location()]})
        data = forecast_response()
        data["current"]["time"] = "2026-10-16T00:00"
        return httpx.Response(200, json=data)

    now = datetime(2026, 10, 15, 16, 5, tzinfo=timezone.utc)
    result = await weather_client(httpx.MockTransport(handler), at=now).forecast(city="江门市")
    assert result["forecast"]["date"] == "2026-10-16"
    assert result["current"]["reference_time"] == "2026-10-16T00:00"


@pytest.mark.asyncio
async def test_stale_forecast_is_not_labelled_as_today():
    """A provider's stale daily array is rejected before it becomes a forecast answer."""

    def handler(request):
        if request.url.host == "geocoding-api.open-meteo.com":
            return httpx.Response(200, json={"results": [location()]})
        data = forecast_response()
        data["daily"]["time"] = ["2026-10-14", "2026-10-15"]
        return httpx.Response(200, json=data)

    result = await weather_client(httpx.MockTransport(handler)).forecast(city="江门市")
    assert "error" in result
    assert "forecast" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("reference", [None, "not-a-date", "2026-10-14T12:15"])
async def test_missing_or_stale_current_weather_is_not_a_current_observation(reference):
    """A valid daily forecast can survive while invalid current conditions are omitted."""

    def handler(request):
        if request.url.host == "geocoding-api.open-meteo.com":
            return httpx.Response(200, json={"results": [location()]})
        data = forecast_response()
        data["current"]["time"] = reference
        return httpx.Response(200, json=data)

    result = await weather_client(httpx.MockTransport(handler)).forecast(city="江门市")
    assert result["current"] is None
    assert result["current_status"] == "stale_or_missing"
    assert result["forecast"]["date"] == "2026-10-16"
