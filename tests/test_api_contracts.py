import pytest
import requests

from adapters.digitransit import default_digitransit_hsl_provider
from adapters.entur import default_entur_provider
from weather import MetWeatherAdapter


@pytest.mark.vcr
def test_entur_live_api_contract(live_or_dummy_app_config):
    """
    Tests live/recorded Entur GraphQL response contract.
    Ensures that Entur's real response deserializes into NormalizedStopData without error.
    """
    session = requests.Session()
    # Oslo S / Jernbanetorget: NSR:StopPlace:58366
    stop_id = "NSR:StopPlace:58366"
    norm = default_entur_provider.fetch_stop(
        session=session,
        clean_id=stop_id,
        time_range_seconds=3600,
        departures_count=5,
        app_config=live_or_dummy_app_config,
    )

    assert norm.name != ""
    assert norm.latitude is not None and 50.0 <= norm.latitude <= 72.0
    assert norm.longitude is not None and 4.0 <= norm.longitude <= 32.0
    assert len(norm.departures) > 0

    first_dep = norm.departures[0]
    assert first_dep.line_code != ""
    assert first_dep.destination != ""
    assert first_dep.transport_mode in ("bus", "tram", "rail", "metro", "ferry", "air")
    assert first_dep.aimed_iso != ""
    assert first_dep.expected_iso != ""


@pytest.mark.vcr
def test_digitransit_live_api_contract(live_or_dummy_app_config):
    """
    Tests live/recorded Digitransit HSL GraphQL response contract.
    Ensures that Digitransit's real response deserializes into NormalizedStopData without error.
    """
    session = requests.Session()
    # Kamppi: HSL:1020455
    stop_id = "HSL:1020455"
    norm = default_digitransit_hsl_provider.fetch_stop(
        session=session,
        clean_id=stop_id,
        time_range_seconds=3600,
        departures_count=5,
        app_config=live_or_dummy_app_config,
    )

    assert norm.name != ""
    assert norm.latitude is not None and 59.0 <= norm.latitude <= 71.0
    assert norm.longitude is not None and 19.0 <= norm.longitude <= 32.0
    assert len(norm.departures) > 0

    first_dep = norm.departures[0]
    assert first_dep.line_code != ""
    assert first_dep.destination != ""
    assert first_dep.transport_mode in ("bus", "tram", "rail", "metro", "ferry", "air")
    assert first_dep.aimed_iso != ""
    assert first_dep.expected_iso != ""


@pytest.mark.vcr
def test_met_norway_live_api_contract(live_or_dummy_app_config):
    """
    Tests live/recorded MET Norway Locationforecast 2.0 response contract.
    Ensures that MET's real JSON response deserializes into WeatherData without error.
    """
    session = requests.Session()
    adapter = MetWeatherAdapter()
    # Oslo coordinates
    weather = adapter.fetch_weather(
        session=session,
        lat=59.9139,
        lon=10.7522,
        app_config=live_or_dummy_app_config,
    )

    assert weather is not None
    assert -60.0 <= weather.temperature_c <= 50.0
    assert weather.wind_ms >= 0.0
    assert 0.0 <= weather.wind_direction_degrees <= 360.0
    assert weather.symbol_code != ""
    assert weather.fetched_at_iso != ""
