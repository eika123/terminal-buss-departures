import json
import logging
from pathlib import Path
from typing import Any, Protocol

import arrow
import requests

from config import (
    REQUEST_TIMEOUT_SECONDS,
    WEATHER_CACHE_DURATION_SECONDS,
    WEATHER_CACHE_FILE,
    ConfigError,
)
from models import WeatherData
from resilience import ConsecutiveFailureTracker

logger = logging.getLogger("avgangstider.weather")


class WeatherCache:
    """Handles reading, writing and caching raw weather forecasts on disk."""

    def __init__(self, cache_path: Path = WEATHER_CACHE_FILE, max_failures: int = 10):
        self.cache_path = cache_path
        self.tracker = ConsecutiveFailureTracker(name="weather_cache", max_failures=max_failures)
        self._data: dict[str, dict[str, Any]] = self._load_from_disk()

    def _load_from_disk(self) -> dict[str, dict[str, Any]]:
        if not self.cache_path.is_file():
            return {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                retval = json.load(f)
                self.tracker.record_success()
                return retval
        except (OSError, json.JSONDecodeError, KeyError) as e:
            self.tracker.record_failure(e)
            return {}

    def _save_to_disk(self) -> None:
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
                self.tracker.record_success()
        except OSError as e:
            self.tracker.record_failure(e)

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
            retval = WeatherData.model_validate(entry)
            self.tracker.record_success()
            return retval
        except (ValueError, KeyError, TypeError) as e:
            self.tracker.record_failure(e)
            return None

    def save_weather(self, lat: float, lon: float, weather: WeatherData) -> None:
        key = self._make_key(lat, lon)
        self._data[key] = weather.model_dump()
        self._save_to_disk()


class WeatherProvider(Protocol):
    """Protocol for fetching weather data from a weather service provider."""

    def fetch_weather(
        self,
        session: requests.Session,
        lat: float,
        lon: float,
        app_config: dict[str, Any],
    ) -> WeatherData | None:
        """Fetch raw weather data for specified coordinates."""
        ...


class MetWeatherAdapter:
    """Weather provider implementation for Meteorologisk institutt (MET Norway)."""

    DEFAULT_API_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"

    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        tracker: ConsecutiveFailureTracker | None = None,
    ) -> None:
        self.api_url = api_url
        self.tracker = tracker or ConsecutiveFailureTracker(name="met_weather_api", max_failures=10)

    def fetch_weather(
        self,
        session: requests.Session,
        lat: float,
        lon: float,
        app_config: dict[str, Any],
    ) -> WeatherData | None:
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
                self.api_url,
                headers=headers,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if res.status_code != 200:
                logger.warning("MET API returned HTTP %s for lat=%s lon=%s", res.status_code, lat, lon)
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

            self.tracker.record_success()
            return observation
        except ConfigError:
            raise
        except (requests.RequestException, ValueError, KeyError) as e:
            self.tracker.record_failure(e)
            return None


class WeatherService:
    """
    Coordinates weather lookups using a cache-first approach.
    Caching is mandatory to respect upstream rate limits and fair-use policies.
    Queries the underlying WeatherProvider only on cache misses or expirations.
    """

    def __init__(
        self,
        cache: WeatherCache,
        provider: WeatherProvider | None = None,
    ) -> None:
        if cache is None:
            raise ValueError("A valid WeatherCache instance is mandatory for WeatherService.")
        self.cache: WeatherCache = cache
        self.provider: WeatherProvider = provider if provider is not None else MetWeatherAdapter()

    def get_weather(
        self,
        session: requests.Session,
        lat: float,
        lon: float,
        app_config: dict[str, Any],
    ) -> WeatherData | None:
        cached = self.cache.get_weather(lat, lon)
        if cached is not None:
            return cached

        observation = self.provider.fetch_weather(session, lat, lon, app_config)
        if observation is not None:
            self.cache.save_weather(lat, lon, observation)

        return observation


# Default service instance constructed explicitly with its own cache
default_weather_service = WeatherService(cache=WeatherCache())
