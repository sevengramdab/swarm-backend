"""Weather integration — free real-time weather via Open-Meteo (no API key required)."""
import json
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_http_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
    return _http_client


# WMO weather interpretation codes → human readable
WMO_CODES: Dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


async def geocode_location(name: str) -> Optional[Dict[str, Any]]:
    """Resolve a location name to lat/lon using Open-Meteo geocoding."""
    try:
        client = get_client()
        resp = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": name, "count": "1", "language": "en", "format": "json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        if results:
            r = results[0]
            return {
                "name": r.get("name", name),
                "country": r.get("country", ""),
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "timezone": r.get("timezone", "auto"),
            }
    except Exception as e:
        logger.warning(f"Geocoding failed for '{name}': {e}")
    return None


async def get_current_weather(location: str) -> str:
    """Fetch current weather for a location and return a human-readable summary."""
    geo = await geocode_location(location)
    if not geo:
        return f"Could not find location: {location}. Please check the spelling or try a nearby city."

    try:
        client = get_client()
        resp = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": geo["latitude"],
                "longitude": geo["longitude"],
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,apparent_temperature",
                "timezone": geo.get("timezone", "auto"),
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})
        temp = current.get("temperature_2m")
        feels_like = current.get("apparent_temperature")
        humidity = current.get("relative_humidity_2m")
        wind = current.get("wind_speed_10m")
        code = current.get("weather_code")
        condition = WMO_CODES.get(code, "Unknown conditions")

        # Convert Celsius to Fahrenheit like switching between metric and imperial units
        # in an AutoCAD drawing -- the underlying geometry doesn't change, just the display.
        def _c_to_f(c: float | None) -> float | None:
            return round(c * 9 / 5 + 32, 1) if c is not None else None

        temp_f = _c_to_f(temp)
        feels_f = _c_to_f(feels_like)

        parts = [
            f"Current weather in {geo['name']}, {geo['country']}: {condition}.",
        ]
        if temp is not None:
            parts.append(f"Temperature: {temp}°C ({temp_f}°F)")
        if feels_like is not None:
            parts.append(f"Feels like: {feels_like}°C ({feels_f}°F)")
        if humidity is not None:
            parts.append(f"Humidity: {humidity}%")
        if wind is not None:
            parts.append(f"Wind: {wind} km/h")
        return " | ".join(parts)
    except Exception as e:
        logger.warning(f"Weather fetch failed for '{location}': {e}")
        return f"Could not retrieve weather for {location} right now. Error: {e}"


async def get_time_at_location(location: str) -> str:
    """Return the current local time for a location using its timezone from geocoding."""
    import datetime
    from zoneinfo import ZoneInfo

    geo = await geocode_location(location)
    if not geo:
        return f"Could not find location: {location}."

    tz_name = geo.get("timezone")
    if not tz_name or tz_name == "auto":
        now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return f"Current time in {geo['name']}, {geo['country']}: {now_utc} (timezone unknown, showing UTC)."

    try:
        tz = ZoneInfo(tz_name)
        now = datetime.datetime.now(tz)
        local_time = now.strftime("%Y-%m-%d %I:%M:%S %p %Z")
        return f"Current time in {geo['name']}, {geo['country']}: {local_time}."
    except Exception as e:
        now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        logger.warning(f"Timezone conversion failed for '{location}' (tz={tz_name}): {e}")
        return f"Current time in {geo['name']}, {geo['country']}: {now_utc} (timezone error, showing UTC)."
