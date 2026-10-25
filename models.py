from pydantic import BaseModel, Field


class WeatherData(BaseModel):
    """Raw meteorological observation data from MET Norway."""

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


class StopPlaceState(BaseModel):
    """State of an observed stop place in the active board session."""

    name: str
    raw_id: str
    clean_id: str
    provider: str
    normalized_data: NormalizedStopData | None = None
    error_message: str | None = None
    last_updated_iso: str | None = None
    weather: WeatherData | None = None

