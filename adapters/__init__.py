import logging
import sys
from typing import Any

import arrow
import requests

from adapters.digitransit import (
    default_digitransit_finland_provider,
    default_digitransit_hsl_provider,
)
from adapters.entur import default_entur_provider
from config import ConfigError
from models import StopPlaceState, TransitProvider
from resilience import ConsecutiveFailureTracker
from weather import WeatherService, default_weather_service

logger = logging.getLogger("avgangstider.adapters")

# Per-stop failure trackers to allow intermittent failures but crash if a stop fails 10 consecutive times
_stop_failure_trackers: dict[str, ConsecutiveFailureTracker] = {}


def get_stop_tracker(stop_key: str) -> ConsecutiveFailureTracker:
    if stop_key not in _stop_failure_trackers:
        _stop_failure_trackers[stop_key] = ConsecutiveFailureTracker(name=f"stop_{stop_key}", max_failures=10)
    return _stop_failure_trackers[stop_key]


# Registry of known TransitProvider implementations
_PROVIDER_REGISTRY: dict[str, TransitProvider] = {
    "entur": default_entur_provider,
    "digitransit_hsl": default_digitransit_hsl_provider,
    "digitransit_finland": default_digitransit_finland_provider,
}


def register_transit_provider(name: str, provider: TransitProvider) -> None:
    """Register or override a TransitProvider in the adapter registry."""
    _PROVIDER_REGISTRY[name] = provider


def get_transit_provider(name: str) -> TransitProvider:
    """Resolve a TransitProvider by name from registry."""
    if name == "resrobot":
        raise NotImplementedError("ResRobot (Sweden) adapter requires API key configuration.")
    if name == "rejseplanen":
        raise NotImplementedError("Rejseplanen (Denmark) adapter requires API key configuration.")
    provider = _PROVIDER_REGISTRY.get(name)
    if provider is None:
        return default_entur_provider
    return provider


def detect_provider(raw_id: str) -> tuple[str, str]:
    """
    Determines provider ('entur', 'digitransit_hsl', 'digitransit_finland', etc.)
    and returns (provider_name, clean_id).
    """
    cleaned = raw_id.strip()
    id_lower = cleaned.lower()

    country_map = {
        "no": "entur",
        "fi": "digitransit_hsl",
        "finland": "digitransit_finland",
        "se": "resrobot",
        "dk": "rejseplanen",
    }

    if ":" in cleaned:
        first_part, rest = cleaned.split(":", 1)
        first_lower = first_part.strip().lower()
        if first_lower in country_map:
            return country_map[first_lower], rest.strip()

    if id_lower.startswith("nsr:"):
        return "entur", cleaned
    if id_lower.startswith(("hsl:", "hki:")):
        return "digitransit_hsl", cleaned
    if id_lower.startswith(("tampere:", "waltti:", "matka:", "vr:")):
        return "digitransit_finland", cleaned

    if id_lower.startswith("74") and len(id_lower) == 9 and id_lower.isdigit():
        return "resrobot", cleaned
    if id_lower.startswith(("0086", "86")) and id_lower.isdigit():
        return "rejseplanen", cleaned

    return "entur", cleaned


def resolve_stop_place_provider(raw_id: str) -> tuple[TransitProvider, str]:
    """Detects provider from stop place ID and resolves the concrete TransitProvider instance."""
    provider_name, clean_id = detect_provider(raw_id)
    return get_transit_provider(provider_name), clean_id


def fetch_and_update_departures(
    session: requests.Session,
    stops_state: dict[str, StopPlaceState],
    time_range_seconds: int,
    departures_count: int,
    app_config: dict[str, Any],
    weather_service: WeatherService | None = None,
) -> None:
    """Fetches departure updates using each stop's TransitProvider, then updates weather."""
    active_weather_service = weather_service or default_weather_service
    for alias_name, state in stops_state.items():
        try:
            norm = state.provider.fetch_stop(
                session=session,
                clean_id=state.clean_id,
                time_range_seconds=time_range_seconds,
                departures_count=departures_count,
                app_config=app_config,
            )

            state.normalized_data = norm
            state.error_message = None
            state.last_updated_iso = arrow.now().isoformat()
            get_stop_tracker(alias_name).record_success()

            if norm.latitude is not None and norm.longitude is not None:
                state.weather = active_weather_service.get_weather(
                    session, norm.latitude, norm.longitude, app_config
                )

        except ConfigError as ce:
            print(f"\nConfiguration Error: {ce}")
            sys.exit(1)
        except LookupError as le:
            state.error_message = f"NOT_FOUND:{le}"
            get_stop_tracker(alias_name).record_failure(le)
        except requests.RequestException as re:
            state.error_message = f"NETWORK:{re}"
            get_stop_tracker(alias_name).record_failure(re)
        except (ValueError, KeyError, TypeError) as e:
            state.error_message = f"API_ERROR:{e}"
            get_stop_tracker(alias_name).record_failure(e)
