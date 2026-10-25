import pytest
import requests

from adapters import detect_provider, fetch_and_update_departures
from adapters.digitransit import fetch_digitransit_stop
from adapters.entur import fetch_entur_stop
from config import ConfigError
from models import StopPlaceState


def test_detect_provider():
    # Explicit prefixes
    assert detect_provider("NO:NSR:StopPlace:123") == ("entur", "NSR:StopPlace:123")
    assert detect_provider("FI:1020455") == ("digitransit_hsl", "1020455")
    assert detect_provider("FINLAND:tampere:001") == ("digitransit_finland", "tampere:001")
    assert detect_provider("SE:740000001") == ("resrobot", "740000001")
    assert detect_provider("DK:8600001") == ("rejseplanen", "8600001")

    # Native prefixes
    assert detect_provider("NSR:StopPlace:53434") == ("entur", "NSR:StopPlace:53434")
    assert detect_provider("HSL:1020455") == ("digitransit_hsl", "HSL:1020455")
    assert detect_provider("tampere:1234") == ("digitransit_finland", "tampere:1234")

    # Numeric fallback
    assert detect_provider("741234567") == ("resrobot", "741234567")
    assert detect_provider("008612345") == ("rejseplanen", "008612345")


def test_fetch_entur_missing_client_name(mocker):
    session = mocker.MagicMock()
    with pytest.raises(ConfigError) as exc_info:
        fetch_entur_stop(session, "NSR:StopPlace:53434", 3600, 5, app_config={})
    assert "ET_CLIENT_NAME" in str(exc_info.value)


def test_fetch_entur_success(mocker):
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "stopPlace": {
                "name": "Klimavegen",
                "latitude": 69.65,
                "longitude": 18.95,
                "estimatedCalls": [
                    {
                        "realtime": True,
                        "aimedArrivalTime": "2026-10-25T12:00:00+02:00",
                        "aimedDepartureTime": "2026-10-25T12:00:00+02:00",
                        "expectedArrivalTime": "2026-10-25T12:02:00+02:00",
                        "expectedDepartureTime": "2026-10-25T12:02:00+02:00",
                        "destinationDisplay": {"frontText": "Sentrum"},
                        "serviceJourney": {
                            "journeyPattern": {
                                "line": {
                                    "publicCode": "28",
                                    "transportMode": "bus"
                                }
                            }
                        }
                    }
                ]
            }
        }
    }
    session = mocker.MagicMock()
    session.post.return_value = mock_resp

    app_config = {"ET_CLIENT_NAME": "test-app"}
    norm = fetch_entur_stop(session, "NSR:StopPlace:53434", 3600, 5, app_config)

    assert norm.name == "Klimavegen"
    assert norm.latitude == 69.65
    assert len(norm.departures) == 1
    dep = norm.departures[0]
    assert dep.line_code == "28"
    assert dep.destination == "Sentrum"
    assert dep.is_realtime is True


def test_fetch_digitransit_missing_subscription_key(mocker):
    session = mocker.MagicMock()
    with pytest.raises(ConfigError) as exc_info:
        fetch_digitransit_stop(session, "1020455", 3600, 5, app_config={})
    assert "DIGITRANSIT_SUBSCRIPTION_KEY" in str(exc_info.value)


def test_fetch_digitransit_success(mocker):
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "stop1": {
                "name": "Kamppi",
                "lat": 60.169,
                "lon": 24.933,
                "stoptimesWithoutPatterns": [
                    {
                        "scheduledDeparture": 3600,
                        "realtimeDeparture": 3660,
                        "realtime": True,
                        "serviceDay": 1700000000,
                        "headsign": "Vuosaari",
                        "trip": {
                            "route": {
                                "shortName": "M1",
                                "mode": "SUBWAY"
                            }
                        }
                    }
                ]
            }
        }
    }
    session = mocker.MagicMock()
    session.post.return_value = mock_resp

    app_config = {"DIGITRANSIT_SUBSCRIPTION_KEY": "fake_key"}
    norm = fetch_digitransit_stop(session, "1020455", 3600, 5, app_config)

    assert norm.name == "Kamppi"
    assert norm.latitude == 60.169
    assert len(norm.departures) == 1
    dep = norm.departures[0]
    assert dep.line_code == "M1"
    assert dep.transport_mode == "metro"
    assert dep.destination == "Vuosaari"


def test_fetch_and_update_departures_handles_error(mocker):
    session = mocker.MagicMock()
    session.post.side_effect = requests.RequestException("Connection refused")

    state = StopPlaceState(
        name="Klimavegen",
        raw_id="NSR:StopPlace:53434",
        clean_id="NSR:StopPlace:53434",
        provider="entur",
    )
    stops_state = {"Klimavegen": state}
    app_config = {"ET_CLIENT_NAME": "test"}

    fetch_and_update_departures(session, stops_state, 3600, 5, app_config)

    assert state.error_message is not None
    assert state.error_message.startswith("NETWORK:")

