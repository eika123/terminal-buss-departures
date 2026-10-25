import arrow
import pytest

from config import ConfigError
from models import WeatherData
from weather import WeatherCache, fetch_weather_from_met


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


def test_fetch_weather_from_met_missing_user_agent(mocker):
    session = mocker.MagicMock()
    with pytest.raises(ConfigError) as exc_info:
        fetch_weather_from_met(session, 60.0, 10.0, app_config={})
    assert "MET_USER_AGENT" in str(exc_info.value)


def test_fetch_weather_from_met_success(mocker, tmp_path):
    # Isolated cache for test
    cache_file = tmp_path / "met_cache.json"
    mocker.patch("weather.weather_cache", WeatherCache(cache_path=cache_file))

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

    app_config = {"MET_USER_AGENT": "TestApp/1.0 (contact@example.com)"}
    weather = fetch_weather_from_met(session, 60.123, 10.456, app_config)

    assert weather is not None
    assert weather.temperature_c == 11.2
    assert weather.wind_ms == 4.5
    assert weather.wind_gust_ms == 7.0
    assert weather.wind_direction_degrees == 220.0
    assert weather.symbol_code == "cloudy"
