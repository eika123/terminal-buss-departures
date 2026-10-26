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
from models import StopPlaceState, TransitProvider, TransitProviderKey
from resilience import ConsecutiveFailureTracker
from weather import WeatherService, default_weather_service

logger = logging.getLogger("avgangstider.adapters")

# Per-stop failure trackers to allow intermittent failures but crash if a stop fails 10 consecutive times
_stop_failure_trackers: dict[str, ConsecutiveFailureTracker] = {}


def get_stop_tracker(stop_key: str) -> ConsecutiveFailureTracker:
    if stop_key not in _stop_failure_trackers:
        _stop_failure_trackers[stop_key] = ConsecutiveFailureTracker(
            name=f"stop_{stop_key}", max_failures=10
        )
    return _stop_failure_trackers[stop_key]


# Registry of known TransitProvider implementations
_PROVIDER_REGISTRY: dict[TransitProviderKey | str, TransitProvider] = {
    "entur": default_entur_provider,
    "digitransit_hsl": default_digitransit_hsl_provider,
    "digitransit_finland": default_digitransit_finland_provider,
}


COUNTRY_PREFIX_MAP: dict[str, TransitProviderKey] = {
    "no": "entur",
    "fi": "digitransit_finland",
    "finland": "digitransit_finland",
    "se": "resrobot",
    "dk": "rejseplanen",
}

# decides what APIs to call based on prefix in stop locations from stoppesteder.txt
PREFIX_TO_PROVIDER_MAP: tuple[tuple[tuple[str, ...], TransitProviderKey], ...] = (
    (("nsr:", "no:"), "entur"),
    (("fi:hsl:", "fi:hki:", "hsl:", "hki:"), "digitransit_hsl"),
    (
        ("fi:tampere:", "fi:nysse:", "fi:waltti:", "fi:matka:", "fi:vr:"),
        "digitransit_finland",
    ),
    (("tampere:", "nysse:", "waltti:", "matka:", "vr:"), "digitransit_finland"),
)


def _detect_numeric_id_provider(id_lower: str) -> TransitProviderKey | None:
    """Matches national stop place numbers (e.g. Sweden 74xxxxxxx, Denmark 86xxxxxx)."""
    if not id_lower.isdigit():
        return None
    if len(id_lower) == 9 and id_lower.startswith("74"):
        return "resrobot"
    return "rejseplanen" if id_lower.startswith(("0086", "86")) else None


def register_transit_provider(
    name: TransitProviderKey | str, provider: TransitProvider
) -> None:
    """Register or override a TransitProvider in the adapter registry."""
    _PROVIDER_REGISTRY[name] = provider


def get_transit_provider(name: TransitProviderKey | str) -> TransitProvider:
    """Resolve a TransitProvider by name from registry."""
    if name == "resrobot":
        raise NotImplementedError(
            "ResRobot (Sweden) adapter requires API key configuration."
        )
    if name == "rejseplanen":
        raise NotImplementedError(
            "Rejseplanen (Denmark) adapter requires API key configuration."
        )
    provider = _PROVIDER_REGISTRY.get(name)
    return default_entur_provider if provider is None else provider


def detect_provider(raw_id: str) -> tuple[TransitProviderKey, str]:
    """
    Determines provider ('entur', 'digitransit_hsl', 'digitransit_finland', etc.)
    and returns (provider_name, clean_id).
    Supports Finnish regional prefixes:
      - 'fi:hsl:...' or 'fi:hki:...' -> digitransit_hsl
      - 'fi:nysse:...', 'fi:tampere:...', 'fi:waltti:...', or 'fi:...' -> digitransit_finland
    """
    cleaned = raw_id.strip()
    id_lower = cleaned.lower()

    if id_lower.startswith("fi:"):
        sub_id = cleaned[3:].strip()
        sub_lower = sub_id.lower()
        if sub_lower.startswith(("hsl:", "hki:")):
            return "digitransit_hsl", sub_id
        return "digitransit_finland", sub_id

    if ":" in cleaned:
        first_part, rest = cleaned.split(":", 1)
        if prov := COUNTRY_PREFIX_MAP.get(first_part.strip().lower()):
            return prov, rest.strip()

    for prefixes, prov_name in PREFIX_TO_PROVIDER_MAP:
        if id_lower.startswith(prefixes):
            return prov_name, cleaned

    if num_prov := _detect_numeric_id_provider(id_lower):
        return num_prov, cleaned

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
