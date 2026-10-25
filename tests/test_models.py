import pytest
from pydantic import ValidationError

from models import DepartureData, NormalizedStopData, StopPlaceState, WeatherData


def test_weather_data_valid():
    w = WeatherData(
        temperature_c=12.5,
        wind_ms=5.0,
        wind_gust_ms=8.2,
        wind_direction_degrees=180.0,
        symbol_code="cloudy",
        fetched_at_iso="2026-10-25T12:00:00+00:00",
    )
    assert w.temperature_c == 12.5
    assert w.wind_gust_ms == 8.2
    assert w.symbol_code == "cloudy"


def test_weather_data_validation_error():
    with pytest.raises(ValidationError):
        # Missing required fields like symbol_code and fetched_at_iso
        WeatherData(temperature_c="invalid_number") # type: ignore


def test_departure_data_valid():
    dep = DepartureData(
        line_code="31",
        transport_mode="bus",
        destination="Grorud",
        aimed_iso="2026-10-25T12:00:00+00:00",
        expected_iso="2026-10-25T12:02:00+00:00",
        is_realtime=True,
    )
    assert dep.line_code == "31"
    assert dep.is_realtime is True


def test_normalized_stop_data():
    dep = DepartureData(
        line_code="7",
        transport_mode="tram",
        destination="Länsisatama",
        aimed_iso="2026-10-25T12:00:00+00:00",
        expected_iso="2026-10-25T12:00:00+00:00",
        is_realtime=False,
    )
    stop = NormalizedStopData(
        name="Senaatintori",
        latitude=60.169,
        longitude=24.950,
        departures=[dep],
    )
    assert stop.name == "Senaatintori"
    assert len(stop.departures) == 1
    assert stop.departures[0].destination == "Länsisatama"


def test_stop_place_state():
    state = StopPlaceState(
        name="Klimavegen",
        raw_id="NSR:StopPlace:53434",
        clean_id="NSR:StopPlace:53434",
        provider="entur",
    )
    assert state.name == "Klimavegen"
    assert state.normalized_data is None
    assert state.weather is None

