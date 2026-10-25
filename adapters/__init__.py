import logging
import sys
from typing import Any

import arrow
import requests

from adapters.digitransit import fetch_digitransit_stop
from adapters.entur import fetch_entur_stop
from config import ConfigError, DIGITRANSIT_FINLAND_URL, DIGITRANSIT_HSL_URL
from models import StopPlaceState
from weather import fetch_weather_from_met


def detect_provider(raw_id: str) -> tuple[str, str]:
    """
    Determines provider ('entur', 'digitransit_hsl', 'digitransit_finland', etc.)
    and returns (provider, clean_id).

    Supports explicit country prefixes:
      - 'NO:...' -> Entur
      - 'FI:...' -> Digitransit HSL
      - 'FINLAND:...' -> Digitransit Finland national
      - 'SE:...' -> ResRobot (Sweden)
      - 'DK:...' -> Rejseplanen (Denmark)

    Or direct native feed IDs:
      - 'NSR:...' -> Entur (Norway)
      - 'HSL:...' or 'HKI:...' -> Digitransit HSL (Helsinki)
      - 'tampere:...', 'waltti:...' -> Digitransit Finland national
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
    if (id_lower.startswith("0086") or id_lower.startswith("86")) and id_lower.isdigit():
        return "rejseplanen", cleaned

    return "entur", cleaned


def fetch_and_update_departures(
    session: requests.Session,
    stops_state: dict[str, StopPlaceState],
    time_range_seconds: int,
    departures_count: int,
    app_config: dict[str, Any],
) -> None:
    """Fetches departure updates using appropriate country/API adapter, then updates weather."""
    for alias_name, state in stops_state.items():
        try:
            if state.provider == "entur":
                norm = fetch_entur_stop(session, state.clean_id, time_range_seconds, departures_count, app_config)
            elif state.provider == "digitransit_hsl":
                norm = fetch_digitransit_stop(session, state.clean_id, time_range_seconds, departures_count, app_config, DIGITRANSIT_HSL_URL)
            elif state.provider == "digitransit_finland":
                norm = fetch_digitransit_stop(session, state.clean_id, time_range_seconds, departures_count, app_config, DIGITRANSIT_FINLAND_URL)
            elif state.provider == "resrobot":
                raise NotImplementedError("ResRobot (Sweden) adapter requires API key configuration.")
            elif state.provider == "rejseplanen":
                raise NotImplementedError("Rejseplanen (Denmark) adapter requires API key configuration.")
            else:
                norm = fetch_entur_stop(session, state.clean_id, time_range_seconds, departures_count, app_config)

            state.normalized_data = norm
            state.error_message = None
            state.last_updated_iso = arrow.now().isoformat()

            if norm.latitude is not None and norm.longitude is not None:
                state.weather = fetch_weather_from_met(session, norm.latitude, norm.longitude, app_config)

        except ConfigError as ce:
            print(f"\nConfiguration Error: {ce}")
            sys.exit(1)
        except LookupError as le:
            state.error_message = f"NOT_FOUND:{le}"
            logging.warning("Stop lookup error for %s (%s, %s): %s", alias_name, state.clean_id, state.provider, le)
        except requests.RequestException as re:
            state.error_message = f"NETWORK:{re}"
            logging.warning("Network error for %s (%s, %s): %s", alias_name, state.clean_id, state.provider, re)
        except (ValueError, Exception) as e:
            state.error_message = f"API_ERROR:{e}"
            logging.warning("API error for %s (%s, %s): %s", alias_name, state.clean_id, state.provider, e)

