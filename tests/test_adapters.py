import pytest
import requests

from adapters import (
    detect_provider,
    fetch_and_update_departures,
    get_transit_provider,
    register_transit_provider,
)
from adapters.digitransit import fetch_digitransit_stop
from adapters.entur import default_entur_provider, fetch_entur_stop
from config import ConfigError
from models import StopPlaceState, TransitProvider


@pytest.mark.parametrize(
    "raw_id,expected_provider,expected_clean_id",
    [
        # Explicit country-code prefixes
        ("NO:NSR:StopPlace:123", "entur", "NSR:StopPlace:123"),
        ("fi:hsl:1020455", "digitransit_hsl", "hsl:1020455"),
        ("fi:hki:1020455", "digitransit_hsl", "hki:1020455"),
        ("fi:nysse:0805", "digitransit_finland", "nysse:0805"),
        ("fi:tampere:1234", "digitransit_finland", "tampere:1234"),
        ("fi:waltti:501", "digitransit_finland", "waltti:501"),
        ("fi:matka:100", "digitransit_finland", "matka:100"),
        ("fi:vr:99", "digitransit_finland", "vr:99"),
        ("fi:0805", "digitransit_finland", "0805"),
        ("FINLAND:tampere:001", "digitransit_finland", "tampere:001"),
        ("SE:740000001", "resrobot", "740000001"),
        ("DK:8600001", "rejseplanen", "8600001"),
        # Native operator prefixes
        ("NSR:StopPlace:53434", "entur", "NSR:StopPlace:53434"),
        ("HSL:1020455", "digitransit_hsl", "HSL:1020455"),
        ("hki:1020455", "digitransit_hsl", "hki:1020455"),
        ("tampere:1234", "digitransit_finland", "tampere:1234"),
        ("nysse:0805", "digitransit_finland", "nysse:0805"),
        ("waltti:501", "digitransit_finland", "waltti:501"),
        ("matka:100", "digitransit_finland", "matka:100"),
        ("vr:99", "digitransit_finland", "vr:99"),
        # Numeric national IDs (Sweden / Denmark)
        ("741234567", "resrobot", "741234567"),
        ("008612345", "rejseplanen", "008612345"),
        ("8612345", "rejseplanen", "8612345"),
        # Generic fallback
        ("generic_stop", "entur", "generic_stop"),
    ],
)
def test_detect_provider(raw_id: str, expected_provider: str, expected_clean_id: str):
    """Verify detect_provider correctly classifies stops by country prefix, operator prefix, or numeric pattern."""
    assert detect_provider(raw_id) == (expected_provider, expected_clean_id)


def test_get_transit_provider_registry_and_errors():
    """Verify get_transit_provider error contracts and custom registration."""
    # ResRobot and Rejseplanen without API keys raise NotImplementedError
    with pytest.raises(NotImplementedError, match="ResRobot"):
        get_transit_provider("resrobot")

    with pytest.raises(NotImplementedError, match="Rejseplanen"):
        get_transit_provider("rejseplanen")

    # Unknown provider falls back to default Entur provider
    assert get_transit_provider("unknown_provider") == default_entur_provider

    # Custom provider registration
    class DummyProvider(TransitProvider):
        @property
        def provider_id(self) -> str:
            return "dummy"

        def fetch_stop(self, *args, **kwargs):
            raise NotImplementedError

    dummy = DummyProvider()
    register_transit_provider("custom_test", dummy)
    assert get_transit_provider("custom_test") == dummy


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
                                "line": {"publicCode": "28", "transportMode": "bus"}
                            }
                        },
                    }
                ],
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
                        "trip": {"route": {"shortName": "M1", "mode": "SUBWAY"}},
                    }
                ],
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
        provider=default_entur_provider,
    )
    stops_state = {"Klimavegen": state}
    app_config = {"ET_CLIENT_NAME": "test"}

    fetch_and_update_departures(session, stops_state, 3600, 5, app_config)

    assert state.error_message is not None
    assert state.error_message.startswith("NETWORK:")


def test_fetch_entur_error_branches(mocker):
    """Verify Entur adapter handles 404, GraphQL errors, and empty stopPlace properly."""
    session = mocker.MagicMock()

    # 404 response
    mock_404 = mocker.MagicMock()
    mock_404.status_code = 404
    session.post.return_value = mock_404
    with pytest.raises(LookupError, match="not found on Entur"):
        fetch_entur_stop(
            session, "NSR:StopPlace:99999", 3600, 5, {"ET_CLIENT_NAME": "test"}
        )

    # GraphQL errors
    mock_gql_err = mocker.MagicMock()
    mock_gql_err.status_code = 200
    mock_gql_err.json.return_value = {"errors": [{"message": "Invalid query syntax"}]}
    session.post.return_value = mock_gql_err
    with pytest.raises(ValueError, match="GraphQL errors"):
        fetch_entur_stop(
            session, "NSR:StopPlace:53434", 3600, 5, {"ET_CLIENT_NAME": "test"}
        )

    # Empty stopPlace returned
    mock_empty = mocker.MagicMock()
    mock_empty.status_code = 200
    mock_empty.json.return_value = {"data": {"stopPlace": None}}
    session.post.return_value = mock_empty
    with pytest.raises(LookupError, match="returned no stopPlace data"):
        fetch_entur_stop(
            session, "NSR:StopPlace:53434", 3600, 5, {"ET_CLIENT_NAME": "test"}
        )


def test_fetch_digitransit_error_branches(mocker):
    """Verify Digitransit adapter handles 401/403, 404, GraphQL errors, and empty data."""
    session = mocker.MagicMock()
    app_config = {"DIGITRANSIT_SUBSCRIPTION_KEY": "fake_key"}

    # 401 Unauthorized
    mock_401 = mocker.MagicMock()
    mock_401.status_code = 401
    session.post.return_value = mock_401
    with pytest.raises(ConfigError, match="Invalid or unauthorized"):
        fetch_digitransit_stop(session, "1020455", 3600, 5, app_config)

    # 404 Not Found
    mock_404 = mocker.MagicMock()
    mock_404.status_code = 404
    session.post.return_value = mock_404
    with pytest.raises(LookupError, match="not found on Digitransit"):
        fetch_digitransit_stop(session, "1020455", 3600, 5, app_config)

    # GraphQL errors
    mock_gql_err = mocker.MagicMock()
    mock_gql_err.status_code = 200
    mock_gql_err.json.return_value = {"errors": [{"message": "Rate limit exceeded"}]}
    session.post.return_value = mock_gql_err
    with pytest.raises(ValueError, match="GraphQL errors"):
        fetch_digitransit_stop(session, "1020455", 3600, 5, app_config)

    # Empty stop data
    mock_empty = mocker.MagicMock()
    mock_empty.status_code = 200
    mock_empty.json.return_value = {"data": {}}
    session.post.return_value = mock_empty
    with pytest.raises(LookupError, match="returned no stop or station data"):
        fetch_digitransit_stop(session, "1020455", 3600, 5, app_config)
