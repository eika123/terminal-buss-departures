from typing import Any, Literal, Protocol, runtime_checkable

import requests
from pydantic import BaseModel, ConfigDict, Field

TransitProviderKey = Literal[
    "entur",
    "digitransit_hsl",
    "digitransit_finland",
    "resrobot",
    "rejseplanen",
]


class WeatherData(BaseModel):
    """Raw meteorological observation data from weather providers (e.g. MET Norway)."""

    temperature_c: float
    wind_ms: float
    wind_gust_ms: float | None = None
    wind_direction_degrees: float
    symbol_code: str
    fetched_at_iso: str


class DepartureData(BaseModel):
    """Raw departure information from transit provider without presentation artifacts."""

    line_code: str
    transport_mode: str
    destination: str
    aimed_iso: str
    expected_iso: str
    is_realtime: bool


class NormalizedStopData(BaseModel):
    """Normalized transit stop data holding coordinates and departure calls."""

    name: str
    latitude: float | None = None
    longitude: float | None = None
    departures: list[DepartureData] = Field(default_factory=list)


@runtime_checkable
class TransitProvider(Protocol):
    """Protocol for fetching normalized departure data from a transit authority API."""

    @property
    def provider_id(self) -> TransitProviderKey | str:
        """Unique identifier of the transit provider (e.g. 'entur', 'digitransit_hsl')."""
        ...

    def fetch_stop(
        self,
        session: requests.Session,
        clean_id: str,
        time_range_seconds: int,
        departures_count: int,
        app_config: dict[str, Any],
    ) -> NormalizedStopData:
        """Fetch and parse live departures into NormalizedStopData."""
        ...


@runtime_checkable
class WeatherProvider(Protocol):
    """Protocol for fetching raw weather data from a weather service provider."""

    def fetch_weather(
        self,
        session: requests.Session,
        lat: float,
        lon: float,
        app_config: dict[str, Any],
    ) -> WeatherData | None:
        """Fetch raw weather data for specified coordinates."""
        ...


class StopPlaceState(BaseModel):
    """State of an observed stop place in the active board session."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    raw_id: str
    clean_id: str
    provider: TransitProvider
    normalized_data: NormalizedStopData | None = None
    error_message: str | None = None
    last_updated_iso: str | None = None
    weather: WeatherData | None = None
    transit_system_id: str | None = None


class StopProfile(BaseModel):
    """Profile grouping a collection of stop places with per-profile options."""

    name: str
    stops: dict[str, str] = Field(default_factory=dict)
    use_normalized_names: bool | None = None
    transit_naming: str | None = None
    options: dict[str, str] = Field(default_factory=dict)
