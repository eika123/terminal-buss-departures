from typing import Any

import requests

from config import REQUEST_TIMEOUT_SECONDS, TRANSITOUS_URL, ConfigError
from models import (
    DepartureData,
    NormalizedStopData,
    TransitProvider,
    TransitProviderKey,
)

TRANSITOUS_MODE_MAP: dict[str, str] = {
    "BUS": "bus",
    "COACH": "bus",
    "TRAM": "tram",
    "SUBWAY": "metro",
    "SUBURBAN": "rail",
    "REGIONAL_RAIL": "rail",
    "REGIONAL_FAST_RAIL": "rail",
    "LONG_DISTANCE": "rail",
    "HIGHSPEED_RAIL": "rail",
    "NIGHT_RAIL": "rail",
    "RAIL": "rail",
    "FERRY": "ferry",
    "AIRPLANE": "air",
}


def _get_transitous_headers(app_config: dict[str, Any]) -> dict[str, str]:
    """Builds User-Agent header from TRANSITOUS_USER_AGENT (or MET_USER_AGENT / ENTUR_CLIENT_NAME)."""
    if user_agent := (
        app_config.get("TRANSITOUS_USER_AGENT")
        or app_config.get("MET_USER_AGENT")
        or app_config.get("ENTUR_CLIENT_NAME")
    ):
        return {"User-Agent": user_agent}
    else:
        raise ConfigError(
            "Missing required config 'TRANSITOUS_USER_AGENT' (or 'MET_USER_AGENT') in .env.\n"
            "Transitous requires contact info in the User-Agent header."
        )


def _parse_transitous_stoptimes(raw_stoptimes: list[dict[str, Any]]) -> list[DepartureData]:
    """Extracts DepartureData items from Transitous /api/v1/stoptimes."""
    departures: list[DepartureData] = []
    for st in raw_stoptimes:
        place = st.get("place") or {}
        aimed_iso = place.get("scheduledDeparture") or place.get("departure")
        if not aimed_iso:
            continue
        expected_iso = place.get("departure") or aimed_iso
        line_code = st.get("displayName") or st.get("routeShortName") or "?"
        raw_mode = (st.get("mode") or "BUS").upper()

        departures.append(
            DepartureData(
                line_code=str(line_code),
                transport_mode=TRANSITOUS_MODE_MAP.get(raw_mode, "bus"),
                destination=st.get("headsign") or "unknown",
                aimed_iso=aimed_iso,
                expected_iso=expected_iso,
                is_realtime=bool(st.get("realTime")),
            )
        )
    return departures


class TransitousTransitProvider(TransitProvider):
    """Transit provider for Germany & Europe via Transitous (MOTIS v2) API."""

    def __init__(self, api_url: str = TRANSITOUS_URL):
        self.api_url = api_url.rstrip("/")

    @property
    def provider_id(self) -> TransitProviderKey | str:
        return "transitous"

    def fetch_stop(
        self,
        session: requests.Session,
        clean_id: str,
        time_range_seconds: int,
        departures_count: int,
        app_config: dict[str, Any],
    ) -> NormalizedStopData:
        stop_id = clean_id.strip()
        headers = _get_transitous_headers(app_config)
        response = session.get(
            f"{self.api_url}/stoptimes",
            params={"stopId": stop_id, "n": departures_count},
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code == 404:
            raise LookupError(f"Stop ID '{clean_id}' not found on Transitous (HTTP 404).")
        if response.status_code == 400:
            raise LookupError(f"Invalid Transitous stop ID '{clean_id}': {response.text}")
        response.raise_for_status()

        payload = response.json()
        place = payload.get("place") or {}
        stop_name = place.get("name") or f"Stop {stop_id}"

        return NormalizedStopData(
            name=stop_name,
            latitude=place.get("lat"),
            longitude=place.get("lon"),
            departures=_parse_transitous_stoptimes(payload.get("stopTimes") or []),
        )


def _collect_transitous_stop_matches(
    items: list[dict[str, Any]],
    cc_upper: str | None,
    prefix: str,
    limit: int,
) -> list[tuple[str, str]]:
    """Filters and formats Transitous geocode items into (name, <cc>:<id>) pairs."""
    results: list[tuple[str, str]] = []
    for item in items:
        if cc_upper and (item.get("country") or "").upper() != cc_upper:
            continue
        stop_id = item.get("id")
        if not stop_id:
            continue
        results.append((item.get("name") or stop_id, f"{prefix}{stop_id}"))
        if len(results) >= limit:
            break
    return results


def search_transitous_stops(
    session: requests.Session,
    query: str,
    app_config: dict[str, Any],
    limit: int = 10,
    country: str | None = "DE",
) -> list[tuple[str, str]]:
    """Search Transitous /api/v1/geocode for stops by name, returning (name, <cc>:<id>)."""
    headers = _get_transitous_headers(app_config)
    resp = session.get(
        f"{TRANSITOUS_URL}/geocode",
        params={"text": query, "type": "STOP"},
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    cc_upper = country.upper() if country else None
    prefix = f"{cc_upper.lower()}:" if cc_upper else ""
    return _collect_transitous_stop_matches(resp.json() or [], cc_upper, prefix, limit)


default_transitous_provider = TransitousTransitProvider()
