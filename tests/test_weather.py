import arrow
import pytest
import requests

from config import ConfigError
from models import WeatherData
from weather import (
    MetWeatherAdapter,
    WeatherCache,
    WeatherService,
)


def test_weather_cache_save_and_get(tmp_path):
    cache_file = tmp_path / "test_cache.json"
    cache = WeatherCache(cache_path=cache_file)

    now_iso = arrow.now().isoformat()
    obs = WeatherData(
        temperature_c=8.0,
        wind_ms=3.5,
        wind_direction_degrees=90.0,
        symbol_code="fair",
        fetched_at_iso=now_iso,
    )

    # Initial get should be None
    assert cache.get_weather(60.169, 24.950) is None

    # Save and get back
    cache.save_weather(60.169, 24.950, obs)
    loaded = cache.get_weather(60.169, 24.950)
    assert loaded is not None
    assert loaded.temperature_c == 8.0
    assert loaded.symbol_code == "fair"


def test_weather_cache_corrupt_file_handling(tmp_path):
    cache_file = tmp_path / "corrupt_cache.json"
    cache_file.write_text("invalid json content")

    cache = WeatherCache(cache_path=cache_file)
    assert cache.get_weather(60.0, 10.0) is None


def test_met_weather_adapter_missing_user_agent(mocker):
    session = mocker.MagicMock()
    adapter = MetWeatherAdapter()
    with pytest.raises(ConfigError) as exc_info:
        adapter.fetch_weather(session, 60.0, 10.0, app_config={})
    assert "MET_USER_AGENT" in str(exc_info.value)


def test_met_weather_adapter_success(mocker):
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "properties": {
            "timeseries": [
                {
                    "data": {
                        "instant": {
                            "details": {
                                "air_temperature": 11.2,
                                "wind_speed": 4.5,
                                "wind_speed_of_gust": 7.0,
                                "wind_from_direction": 220.0,
                            }
                        },
                        "next_1_hours": {
                            "summary": {
                                "symbol_code": "cloudy"
                            }
                        }
                    }
                }
            ]
        }
    }
    session = mocker.MagicMock()
    session.get.return_value = mock_resp

    adapter = MetWeatherAdapter()
    app_config = {"MET_USER_AGENT": "TestApp/1.0 (contact@example.com)"}
    weather = adapter.fetch_weather(session, 60.123, 10.456, app_config)

    assert weather is not None
    assert weather.temperature_c == 11.2
    assert weather.wind_ms == 4.5
    assert weather.wind_gust_ms == 7.0
    assert weather.wind_direction_degrees == 220.0
    assert weather.symbol_code == "cloudy"


def test_weather_service_uses_cache_on_hit(mocker, tmp_path):
    cache_file = tmp_path / "svc_cache.json"
    cache = WeatherCache(cache_path=cache_file)

    now_iso = arrow.now().isoformat()
    cached_obs = WeatherData(
        temperature_c=15.0,
        wind_ms=2.0,
        wind_direction_degrees=180.0,
        symbol_code="clearsky_day",
        fetched_at_iso=now_iso,
    )
    cache.save_weather(59.91, 10.75, cached_obs)

    mock_provider = mocker.MagicMock()
    service = WeatherService(provider=mock_provider, cache=cache)

    session = mocker.MagicMock()
    res = service.get_weather(session, 59.91, 10.75, app_config={})

    assert res is not None
    assert res.temperature_c == 15.0
    assert mock_provider.fetch_weather.call_count == 0


def test_weather_service_fetches_and_caches_on_miss(mocker, tmp_path):
    cache_file = tmp_path / "svc_cache_miss.json"
    cache = WeatherCache(cache_path=cache_file)

    now_iso = arrow.now().isoformat()
    fresh_obs = WeatherData(
        temperature_c=18.5,
        wind_ms=5.0,
        wind_direction_degrees=270.0,
        symbol_code="rain",
        fetched_at_iso=now_iso,
    )

    mock_provider = mocker.MagicMock()
    mock_provider.fetch_weather.return_value = fresh_obs

    service = WeatherService(provider=mock_provider, cache=cache)
    session = mocker.MagicMock()
    res = service.get_weather(session, 59.91, 10.75, app_config={"MET_USER_AGENT": "Test/1.0"})

    assert res == fresh_obs
    assert mock_provider.fetch_weather.call_count == 1

    # Next call should hit cache without provider call
    res_second = service.get_weather(session, 59.91, 10.75, app_config={"MET_USER_AGENT": "Test/1.0"})
    assert res_second == fresh_obs
    assert mock_provider.fetch_weather.call_count == 1


def test_weather_service_requires_cache():
    with pytest.raises(ValueError, match="mandatory"):
        WeatherService(cache=None)  # type: ignore


def test_met_weather_adapter_error_handling(mocker):
    """Verify MET Norway weather adapter handles 404 response and network errors."""
    session = mocker.MagicMock()
    adapter = MetWeatherAdapter()
    app_config = {"MET_USER_AGENT": "TestApp/1.0"}

    # 404 returns None (or handles location out of forecast grid)
    mock_404 = mocker.MagicMock()
    mock_404.status_code = 404
    session.get.return_value = mock_404
    assert adapter.fetch_weather(session, 0.0, 0.0, app_config) is None

    # RequestException returns None without crashing
    session.get.side_effect = requests.RequestException("DNS lookup failed")
    assert adapter.fetch_weather(session, 60.0, 10.0, app_config) is None
