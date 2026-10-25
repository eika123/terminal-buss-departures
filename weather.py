import json
import logging
from pathlib import Path
from typing import Any

import arrow
import requests

from config import (
    ConfigError,
    MET_LOCATIONFORECAST_URL,
    REQUEST_TIMEOUT_SECONDS,
    WEATHER_CACHE_DURATION_SECONDS,
    WEATHER_CACHE_FILE,
)
from models import WeatherData


class WeatherCache:
    """Handles reading, writing and caching raw weather forecasts on disk."""

    def __init__(self, cache_path: Path = WEATHER_CACHE_FILE):
        self.cache_path = cache_path
        self._data: dict[str, dict[str, Any]] = self._load_from_disk()

    def _load_from_disk(self) -> dict[str, dict[str, Any]]:
        if not self.cache_path.is_file():
            return {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.warning("Failed to read weather cache: %s", e)
            return {}

    def _save_to_disk(self) -> None:
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.warning(f"Failed to save weather cache: {e}")

    @staticmethod
    def _make_key(lat: float, lon: float) -> str:
        return f"{lat:.3f},{lon:.3f}"

    def get_weather(self, lat: float, lon: float) -> WeatherData | None:
        key = self._make_key(lat, lon)
        entry = self._data.get(key)
        if not entry:
            return None

        try:
            fetched_time = arrow.get(entry["fetched_at_iso"])
            age_seconds = (arrow.now() - fetched_time).total_seconds()
            if age_seconds > WEATHER_CACHE_DURATION_SECONDS:
                return None
            return WeatherData.model_validate(entry)
        except Exception:
            return None

    def save_weather(self, lat: float, lon: float, weather: WeatherData) -> None:
        key = self._make_key(lat, lon)
        self._data[key] = weather.model_dump()
        self._save_to_disk()


weather_cache = WeatherCache()


def fetch_weather_from_met(
    session: requests.Session,
    lat: float,
    lon: float,
    app_config: dict[str, Any],
) -> WeatherData | None:
    """Fetches raw current weather observation from MET Norway with caching."""
    cached = weather_cache.get_weather(lat, lon)
    if cached is not None:
        return cached

    user_agent = app_config.get("MET_USER_AGENT")
    if not user_agent or not str(user_agent).strip():
        raise ConfigError(
            "Missing required config 'MET_USER_AGENT' in .env.\n"
            "Meteorologisk institutt (MET Norway) requires that all clients identify themselves\n"
            "with an application name and contact info (e.g. email or URL).\n"
            "Example in .env: MET_USER_AGENT=\"MyTransitApp/1.0 (contact: user@example.com)\""
        )

    headers = {
        "User-Agent": str(user_agent).strip(),
        "Accept": "application/json",
    }
    params = {"lat": f"{lat:.4f}", "lon": f"{lon:.4f}"}

    try:
        res = session.get(
            MET_LOCATIONFORECAST_URL,
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if res.status_code != 200:
            logging.warning("MET API returned HTTP %s for lat=%s lon=%s", res.status_code, lat, lon)
            return None

        body = res.json()
        now_timeseries = body["properties"]["timeseries"][0]["data"]
        instant = now_timeseries["instant"]["details"]
        temp = instant.get("air_temperature", 0.0)
        wind = instant.get("wind_speed", 0.0)
        wind_gust_raw = instant.get("wind_speed_of_gust")
        wind_gust = float(wind_gust_raw) if wind_gust_raw is not None else None
        wind_dir = float(instant.get("wind_from_direction", 0.0))

        next_1h = now_timeseries.get("next_1_hours") or now_timeseries.get("next_6_hours") or {}
        summary = next_1h.get("summary", {})
        raw_symbol = summary.get("symbol_code", "clearsky")

        observation = WeatherData(
            temperature_c=float(temp),
            wind_ms=float(wind),
            wind_gust_ms=wind_gust,
            wind_direction_degrees=wind_dir,
            symbol_code=raw_symbol,
            fetched_at_iso=arrow.now().isoformat(),
        )

        weather_cache.save_weather(lat, lon, observation)
        return observation
    except Exception as e:
        logging.warning("Error fetching weather: %s", e)
        return None

