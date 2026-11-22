from typing import Any

import arrow
import requests

from config import REJSEPLANEN_URL, REQUEST_TIMEOUT_SECONDS, ConfigError
from models import (
    DepartureData,
    NormalizedStopData,
    TransitProvider,
    TransitProviderKey,
)

REJSEPLANEN_LOCATION_URL = "https://www.rejseplanen.dk/api/location.name"

REJSEPLANEN_CAT_CODE_MAP: dict[str, str] = {
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


def _map_rejseplanen_mode(dep: dict[str, Any]) -> str:
    """Maps a Rejseplanen Departure record to a normalized transport_mode."""
    products = dep.get("Product") or []
    prod = (
        products[0]
        if isinstance(products, list) and products
        else dep.get("ProductAtStop", {})
    )
    cat_code = str(prod.get("catCode", "")).strip()
    if cat_code in REJSEPLANEN_CAT_CODE_MAP:
        return REJSEPLANEN_CAT_CODE_MAP[cat_code]

    cat_out = (prod.get("catOutS") or prod.get("catOutL") or "").upper()
    if "METRO" in cat_out:
        return "metro"
    if "LETBANE" in cat_out or "TRAM" in cat_out:
        return "tram"
    if "TOG" in cat_out or "S-TOG" in cat_out or "RAIL" in cat_out:
        return "rail"
    if "FÆRGE" in cat_out or "FERRY" in cat_out:
        return "ferry"
    return "bus"


def _parse_rejseplanen_datetime(date_str: str | None, time_str: str | None) -> str | None:
    """Parses Rejseplanen date (YYYY-MM-DD) and time (HH:MM:SS) in Europe/Copenhagen."""
    if not date_str or not time_str:
        return None
    return arrow.get(
        f"{date_str} {time_str}",
        "YYYY-MM-DD HH:mm:ss",
        tzinfo="Europe/Copenhagen",
    ).isoformat()


def _parse_rejseplanen_departures(raw_deps: list[dict[str, Any]]) -> list[DepartureData]:
    """Extracts DepartureData items from Rejseplanen Departure list."""
    departures: list[DepartureData] = []
    for dep in raw_deps:
        prod = dep.get("ProductAtStop") or {}
        if not prod and isinstance(dep.get("Product"), list) and dep["Product"]:
            prod = dep["Product"][0]

        line_code = (
            prod.get("displayNumber")
            or prod.get("line")
            or prod.get("num")
            or dep.get("name")
            or "?"
        )
        aimed_iso = _parse_rejseplanen_datetime(dep.get("date"), dep.get("time"))
        if not aimed_iso:
            continue

        rt_iso = _parse_rejseplanen_datetime(dep.get("rtDate"), dep.get("rtTime"))
        expected_iso = rt_iso or aimed_iso

        departures.append(
            DepartureData(
                line_code=str(line_code),
                transport_mode=_map_rejseplanen_mode(dep),
                destination=dep.get("direction") or "unknown",
                aimed_iso=aimed_iso,
                expected_iso=expected_iso,
                is_realtime=rt_iso is not None,
            )
        )
    return departures


class RejseplanenTransitProvider(TransitProvider):
    """Transit provider for Danish public transit via Rejseplanen 2.0 API."""

    def __init__(self, api_url: str = REJSEPLANEN_URL):
        self.api_url = api_url

    @property
    def provider_id(self) -> TransitProviderKey | str:
        return "rejseplanen"

    def fetch_stop(
        self,
        session: requests.Session,
        clean_id: str,
        time_range_seconds: int,
        departures_count: int,
        app_config: dict[str, Any],
    ) -> NormalizedStopData:
        api_key = app_config.get("REJSEPLANEN_SUBSCRIPTION_KEY")
        if not api_key:
            raise ConfigError(
                "Missing required config 'REJSEPLANEN_SUBSCRIPTION_KEY' in .env.\n"
                "Register for a Rejseplanen API key at: https://www.rejseplanen.dk/"
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

        if response.status_code in (401, 403):
            raise ConfigError("Invalid or unauthorized 'REJSEPLANEN_SUBSCRIPTION_KEY'.")
        if response.status_code == 404:
            raise LookupError(f"Stop ID '{clean_id}' not found on Rejseplanen (HTTP 404).")
        if response.status_code == 400:
            try:
                err_payload = response.json()
                msg = err_payload.get("errorText") or err_payload.get("errorCode") or response.text
            except ValueError:
                msg = response.text
            raise LookupError(f"Invalid Rejseplanen stop ID '{clean_id}': {msg}")
        response.raise_for_status()

        payload = response.json()
        if "errorCode" in payload or "errorText" in payload:
            msg = payload.get("errorText") or payload.get("errorCode")
            raise LookupError(f"Rejseplanen error for '{clean_id}': {msg}")

        raw_deps = payload.get("Departure") or []
        stop_name = (
            raw_deps[0].get("stop") if raw_deps else None
        ) or f"Stop {clean_id}"

        return NormalizedStopData(
            name=stop_name,
            departures=_parse_rejseplanen_departures(raw_deps),
        )


def search_rejseplanen_stops(
    session: requests.Session,
    query: str,
    app_config: dict[str, Any],
    limit: int = 10,
    city: str | None = None,
) -> list[tuple[str, str]]:
    """Search Rejseplanen for Danish stops by name, returning (name, dk:<extId>)."""
    api_key = app_config.get("REJSEPLANEN_SUBSCRIPTION_KEY")
    if not api_key:
        raise ConfigError("Missing required config 'REJSEPLANEN_SUBSCRIPTION_KEY' in .env.")

    resp = session.get(
        REJSEPLANEN_LOCATION_URL,
        params={
            "input": query,
            "maxNo": limit * 3 if city else limit,
            "format": "json",
            "accessId": api_key,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    city_lower = city.strip().lower() if city else None
    results: list[tuple[str, str]] = []
    for item in resp.json().get("stopLocationOrCoordLocation") or []:
        stop = item.get("StopLocation")
        if not stop or not stop.get("extId"):
            continue
        name = stop.get("name") or stop["extId"]
        if city_lower and city_lower not in name.lower():
            continue
        results.append((name, f"dk:{stop['extId']}"))
        if len(results) >= limit:
            break
    return results


default_rejseplanen_provider = RejseplanenTransitProvider()
