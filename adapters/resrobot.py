from typing import Any

import arrow
import requests

from config import REQUEST_TIMEOUT_SECONDS, RESROBOT_URL, ConfigError
from models import (
    DepartureData,
    NormalizedStopData,
    TransitProvider,
    TransitProviderKey,
)

# ResRobot v2.1 catCode / catOutS mapping to normalized transport_mode
RESROBOT_CAT_CODE_MAP: dict[str, str] = {
    "0": "air",
    "1": "rail",
    "2": "rail",
    "3": "rail",
    "4": "rail",
    "5": "metro",
    "6": "tram",
    "7": "bus",
    "8": "ferry",
    "9": "bus",
}


_RESROBOT_CAT_OUT_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("TUNNEL", "METRO"), "metro"),
    (("SPÅRV", "TRAM"), "tram"),
    (("TÅG", "PENDEL", "RAIL"), "rail"),
    (("FÄRJA", "BÅT", "FERRY"), "ferry"),
)


def _extract_resrobot_product(dep: dict[str, Any], prefer_at_stop: bool = False) -> dict[str, Any]:
    """Extracts the primary product metadata dict from a ResRobot departure."""
    products = dep.get("Product")
    first_product = products[0] if isinstance(products, list) and products else {}
    at_stop = dep.get("ProductAtStop") or {}
    if prefer_at_stop:
        return at_stop or first_product
    return first_product or at_stop


def _map_resrobot_mode(dep: dict[str, Any]) -> str:
    """Maps a ResRobot Departure record to a normalized transport_mode."""
    prod = _extract_resrobot_product(dep)
    cat_code = str(prod.get("catCode", "")).strip()
    if cat_code in RESROBOT_CAT_CODE_MAP:
        return RESROBOT_CAT_CODE_MAP[cat_code]

    cat_out = (prod.get("catOutS") or prod.get("catOutL") or "").upper()
    for keywords, mode in _RESROBOT_CAT_OUT_KEYWORDS:
        if any(kw in cat_out for kw in keywords):
            return mode
    return "bus"


def _parse_resrobot_datetime(date_str: str | None, time_str: str | None) -> str | None:
    """Parses ResRobot date (YYYY-MM-DD) and time (HH:MM:SS) in Europe/Stockholm."""
    if not date_str or not time_str:
        return None
    return arrow.get(f"{date_str} {time_str}", "YYYY-MM-DD HH:mm:ss", tzinfo="Europe/Stockholm").isoformat()


def _parse_single_resrobot_departure(dep: dict[str, Any]) -> DepartureData | None:
    """Converts a single ResRobot departure dict into DepartureData, or None if invalid."""
    aimed_iso = _parse_resrobot_datetime(dep.get("date"), dep.get("time"))
    if not aimed_iso:
        return None

    prod = _extract_resrobot_product(dep, prefer_at_stop=True)
    line_code = (
        prod.get("displayNumber")
        or prod.get("line")
        or prod.get("num")
        or "?"
    )
    rt_iso = _parse_resrobot_datetime(dep.get("rtDate"), dep.get("rtTime"))
    return DepartureData(
        line_code=str(line_code),
        transport_mode=_map_resrobot_mode(dep),
        destination=dep.get("direction") or "unknown",
        aimed_iso=aimed_iso,
        expected_iso=rt_iso or aimed_iso,
        is_realtime=rt_iso is not None,
    )


def _parse_resrobot_departures(raw_deps: list[dict[str, Any]]) -> list[DepartureData]:
    """Extracts DepartureData items from ResRobot v2.1 Departure list."""
    departures: list[DepartureData] = []
    for dep in raw_deps:
        if parsed := _parse_single_resrobot_departure(dep):
            departures.append(parsed)
    return departures


def _validate_resrobot_response(
    response: requests.Response, clean_id: str
) -> dict[str, Any]:
    """Validates a ResRobot HTTP response and returns the parsed JSON payload."""
    if response.status_code in {401, 403}:
        raise ConfigError("Invalid or unauthorized 'RESROBOT_SUBSCRIPTION_KEY'.")
    if response.status_code == 404:
        raise LookupError(f"Stop ID '{clean_id}' not found on ResRobot (HTTP 404).")
    if response.status_code == 400:
        try:
            err_payload = response.json()
            msg = err_payload.get("errorText") or err_payload.get("errorCode") or response.text
        except ValueError:
            msg = response.text
        raise LookupError(f"Invalid ResRobot stop ID '{clean_id}': {msg}")
    response.raise_for_status()

    payload: dict[str, Any] = response.json()
    if "errorCode" in payload or "errorText" in payload:
        msg = payload.get("errorText") or payload.get("errorCode")
        raise LookupError(f"ResRobot error for '{clean_id}': {msg}")
    return payload


class ResRobotTransitProvider(TransitProvider):
    """Transit provider for Swedish public transit via Trafiklab ResRobot v2.1."""

    def __init__(self, api_url: str = RESROBOT_URL):
        self.api_url = api_url

    @property
    def provider_id(self) -> TransitProviderKey | str:
        return "resrobot"

    def fetch_stop(
        self,
        session: requests.Session,
        clean_id: str,
        time_range_seconds: int,
        departures_count: int,
        app_config: dict[str, Any],
    ) -> NormalizedStopData:
        api_key = app_config.get("RESROBOT_SUBSCRIPTION_KEY")
        if not api_key:
            raise ConfigError(
                "Missing required config 'RESROBOT_SUBSCRIPTION_KEY' in .env.\n"
                "Register for a free Trafiklab ResRobot v2.1 key at: https://www.trafiklab.se/"
            )

        params = {
            "id": clean_id.strip(),
            "duration": max(1, time_range_seconds // 60),
            "maxJourneys": departures_count,
            "format": "json",
            "accessId": api_key,
        }
        response = session.get(
            self.api_url,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        payload = _validate_resrobot_response(response, clean_id)

        raw_deps = payload.get("Departure") or []
        stop_name = (
            raw_deps[0].get("stop") if raw_deps else None
        ) or f"Stop {clean_id}"

        return NormalizedStopData(
            name=stop_name,
            departures=_parse_resrobot_departures(raw_deps),
        )


RESROBOT_LOCATION_URL = "https://api.resrobot.se/v2.1/location.name"


def _collect_resrobot_stop_matches(
    locations: list[dict[str, Any]],
    city_lower: str | None,
    limit: int,
) -> list[tuple[str, str]]:
    """Filters ResRobot location items into (name, se:<extId>) pairs."""
    results: list[tuple[str, str]] = []
    for item in locations:
        stop = item.get("StopLocation")
        if not stop or not stop.get("extId"):
            continue
        name = stop.get("name") or stop["extId"]
        if city_lower and city_lower not in name.lower():
            continue
        results.append((name, f"se:{stop['extId']}"))
        if len(results) >= limit:
            break
    return results


def search_resrobot_stops(
    session: requests.Session,
    query: str,
    app_config: dict[str, Any],
    limit: int = 10,
    city: str | None = None,
) -> list[tuple[str, str]]:
    """Search ResRobot v2.1 for Swedish stops by name, returning (name, se:<extId>)."""
    api_key = app_config.get("RESROBOT_SUBSCRIPTION_KEY")
    if not api_key:
        raise ConfigError("Missing required config 'RESROBOT_SUBSCRIPTION_KEY' in .env.")

    resp = session.get(
        RESROBOT_LOCATION_URL,
        params={"input": query, "maxNo": limit * 3 if city else limit, "format": "json", "accessId": api_key},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    city_lower = city.strip().lower() if city else None
    locations = resp.json().get("stopLocationOrCoordLocation") or []
    return _collect_resrobot_stop_matches(locations, city_lower, limit)


default_resrobot_provider = ResRobotTransitProvider()
