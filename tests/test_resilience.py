import pytest
import requests
from requests.adapters import HTTPAdapter

from adapters import _stop_failure_trackers, fetch_and_update_departures
from adapters.entur import default_entur_provider
from models import DepartureData, NormalizedStopData, StopPlaceState, TransitProvider
from presenters import StopPlacePresenter
from resilience import (
    ConsecutiveFailureTracker,
    MaxConsecutiveFailuresExceeded,
    create_resilient_session,
)


@pytest.fixture(autouse=True)
def reset_failure_trackers():
    """Clear shared adapter failure trackers between tests."""
    _stop_failure_trackers.clear()
    yield
    _stop_failure_trackers.clear()


@pytest.mark.parametrize("prefix", ["https://api.entur.io", "http://digitransit.fi"])
def test_resilient_session_configuration(prefix: str):
    """Verify create_resilient_session configures urllib3 Retry and adapters correctly."""
    session = create_resilient_session(
        retries=4, backoff_factor=0.25, status_forcelist=(429, 500, 503)
    )

    adapter = session.get_adapter(prefix)
    assert isinstance(adapter, HTTPAdapter)
    retries = adapter.max_retries
    assert retries is not None
    assert retries.total == 4
    assert retries.connect == 4
    assert retries.read == 4
    assert retries.status == 4
    assert retries.backoff_factor == 0.25
    assert set(retries.status_forcelist) == {429, 500, 503}


def test_consecutive_failure_tracker_lifecycle():
    """Test ConsecutiveFailureTracker incrementing, recovery reset, and threshold breach."""
    tracker = ConsecutiveFailureTracker(name="test_station", max_failures=3)
    assert tracker.failure_count == 0

    # First failure
    tracker.record_failure(requests.exceptions.ConnectionError("Drop 1"))
    assert tracker.failure_count == 1

    # Recovery resets counter
    tracker.record_success()
    assert tracker.failure_count == 0

    # 3 consecutive failures stay within limit (<= max_failures)
    tracker.record_failure(requests.exceptions.Timeout("Drop 1"))
    assert tracker.failure_count == 1
    tracker.record_failure(requests.exceptions.Timeout("Drop 2"))
    assert tracker.failure_count == 2
    tracker.record_failure(requests.exceptions.Timeout("Drop 3"))
    assert tracker.failure_count == 3

    # 4th consecutive failure exceeds threshold (> max_failures)
    with pytest.raises(MaxConsecutiveFailuresExceeded) as exc_info:
        tracker.record_failure(requests.exceptions.ConnectionError("Fatal drop"))

    assert "exceeded maximum consecutive failures limit (3)" in str(exc_info.value)
    assert "test_station" in str(exc_info.value)


def test_chaos_intermittent_network_drop_preserves_offline_cache(mocker):
    """
    Chaos test: Verify that an intermittent network outage preserves cached departure data
    and marks the state with a NETWORK error, then recovers cleanly on reconnection.
    """
    mock_provider = mocker.MagicMock(spec=TransitProvider)

    initial_departures = [
        DepartureData(
            line_code="31",
            transport_mode="bus",
            destination="Snarøya",
            aimed_iso="2026-10-25T14:00:00+02:00",
            expected_iso="2026-10-25T14:02:00+02:00",
            is_realtime=True,
        )
    ]
    initial_norm = NormalizedStopData(
        name="Jernbanetorget",
        latitude=59.91,
        longitude=10.75,
        departures=initial_departures,
    )

    state = StopPlaceState(
        name="Jernbanetorget",
        raw_id="NSR:StopPlace:58366",
        clean_id="NSR:StopPlace:58366",
        provider=mock_provider,
        normalized_data=initial_norm,
    )
    stops_state = {"Jernbanetorget": state}
    session = requests.Session()
    app_config = {
        "ET_CLIENT_NAME": "test",
        "MET_USER_AGENT": "TestApp/1.0 (contact: user@example.com)",
    }

    # Cycle 1: Network drop (ConnectionError)
    mock_provider.fetch_stop.side_effect = requests.exceptions.ConnectionError(
        "Temporary network drop"
    )
    fetch_and_update_departures(session, stops_state, 3600, 5, app_config)

    assert state.error_message is not None
    assert state.error_message.startswith("NETWORK:Temporary network drop")
    # Crucial offline resilience check: cached departures must NOT be lost!
    assert state.normalized_data is not None
    assert len(state.normalized_data.departures) == 1
    assert state.normalized_data.departures[0].line_code == "31"

    # Cycle 2: Network recovers
    recovered_norm = NormalizedStopData(
        name="Jernbanetorget",
        latitude=59.91,
        longitude=10.75,
        departures=[
            DepartureData(
                line_code="31",
                transport_mode="bus",
                destination="Snarøya",
                aimed_iso="2026-10-25T14:10:00+02:00",
                expected_iso="2026-10-25T14:10:00+02:00",
                is_realtime=True,
            )
        ],
    )
    mock_provider.fetch_stop.side_effect = None
    mock_provider.fetch_stop.return_value = recovered_norm

    mock_weather = mocker.MagicMock()
    mock_weather.get_weather.return_value = None

    fetch_and_update_departures(
        session, stops_state, 3600, 5, app_config, weather_service=mock_weather
    )

    assert state.error_message is None
    assert state.normalized_data is not None
    assert state.normalized_data.departures[0].aimed_iso == "2026-10-25T14:10:00+02:00"


def _trigger_consecutive_fetch_failures(
    session: requests.Session,
    stops_state: dict[str, StopPlaceState],
    app_config: dict[str, str],
    count: int,
) -> None:
    """Helper to repeatedly trigger fetch failures without for-loops inside test body."""
    for _ in range(count):
        fetch_and_update_departures(session, stops_state, 3600, 5, app_config)


def test_chaos_persistent_network_outage_raises_max_failures(mocker):
    """
    Chaos test: Verify that 11 consecutive network failures trigger MaxConsecutiveFailuresExceeded.
    """
    mock_provider = mocker.MagicMock(spec=TransitProvider)
    mock_provider.fetch_stop.side_effect = requests.exceptions.ConnectTimeout(
        "Upstream offline"
    )

    state = StopPlaceState(
        name="Oslo S",
        raw_id="NSR:StopPlace:58366",
        clean_id="NSR:StopPlace:58366",
        provider=mock_provider,
    )
    stops_state = {"Oslo S": state}
    session = requests.Session()
    app_config = {"ET_CLIENT_NAME": "test"}

    # 10 failures should be tolerated without crashing
    _trigger_consecutive_fetch_failures(session, stops_state, app_config, 10)
    assert state.error_message is not None

    # 11th consecutive failure must raise MaxConsecutiveFailuresExceeded
    with pytest.raises(MaxConsecutiveFailuresExceeded):
        fetch_and_update_departures(session, stops_state, 3600, 5, app_config)


def test_chaos_api_corruption_error_handling(mocker):
    """Chaos test: Verify invalid JSON or unexpected API schema is caught as API_ERROR."""
    mock_provider = mocker.MagicMock(spec=TransitProvider)
    mock_provider.fetch_stop.side_effect = TypeError(
        "Malformed payload: expected list, got int"
    )

    state = StopPlaceState(
        name="Kamppi",
        raw_id="HSL:1020455",
        clean_id="1020455",
        provider=mock_provider,
    )
    stops_state = {"Kamppi": state}
    session = requests.Session()

    fetch_and_update_departures(session, stops_state, 3600, 5, app_config={})

    assert state.error_message is not None
    assert state.error_message.startswith("API_ERROR:")


def test_presenter_renders_offline_state_with_cached_departures(capsys):
    """Verify presenter renders cached departures along with offline badge when last_updated_iso exists."""
    norm = NormalizedStopData(
        name="Jernbanetorget",
        latitude=59.91,
        longitude=10.75,
        departures=[
            DepartureData(
                line_code="12",
                transport_mode="tram",
                destination="Majorstuen",
                aimed_iso="2026-10-25T15:00:00+02:00",
                expected_iso="2026-10-25T15:05:00+02:00",
                is_realtime=False,
            )
        ],
    )
    state = StopPlaceState(
        name="Jernbanetorget",
        raw_id="NSR:StopPlace:58366",
        clean_id="58366",
        provider=default_entur_provider,
        normalized_data=norm,
        last_updated_iso="2026-10-25T14:50:00+02:00",
        error_message="NETWORK:Connection reset by peer",
    )

    presenter = StopPlacePresenter(lang="en")
    presenter.render(state)

    captured = capsys.readouterr().out
    assert "Jernbanetorget" in captured
    assert "Majorstuen" in captured
    assert "📡" in captured
    assert "Offline mode" in captured or "offline" in captured.lower()


def test_presenter_renders_offline_state_without_cached_data(capsys):
    """Verify presenter renders clean offline error message when no previous data was cached."""
    state = StopPlaceState(
        name="Jernbanetorget",
        raw_id="NSR:StopPlace:58366",
        clean_id="58366",
        provider=default_entur_provider,
        normalized_data=None,
        last_updated_iso=None,
        error_message="NETWORK:Connection refused",
    )

    presenter = StopPlacePresenter(lang="en")
    presenter.render(state)

    captured = capsys.readouterr().out
    assert "Jernbanetorget" in captured
    assert "📡 Network offline" in captured
