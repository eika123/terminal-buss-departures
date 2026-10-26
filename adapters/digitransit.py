import textwrap
import time
from typing import Any

import arrow
import requests

from config import (
    DIGITRANSIT_FINLAND_URL,
    DIGITRANSIT_HSL_URL,
    REQUEST_TIMEOUT_SECONDS,
    ConfigError,
)
from models import (
    DepartureData,
    NormalizedStopData,
    TransitProvider,
    TransitProviderKey,
)

DIGITRANSIT_MODE_MAP: dict[str, str] = {
    "BUS": "bus",
    "TRAM": "tram",
    "RAIL": "rail",
    "SUBWAY": "metro",
    "FERRY": "ferry",
    "AIRPLANE": "air",
}


def _parse_digitransit_stoptimes(
    stoptimes: list[dict[str, Any]],
) -> list[DepartureData]:
    """Extracts DepartureData items from Digitransit stoptimesWithoutPatterns."""
    departures: list[DepartureData] = []
    current_time = int(time.time())

    for st in stoptimes:
        trip = st.get("trip", {})
        route = trip.get("route", {})
        line_code = route.get("shortName") or "?"
        raw_mode = (route.get("mode") or "BUS").upper()
        mode = DIGITRANSIT_MODE_MAP.get(raw_mode, "bus")
        dest = st.get("headsign") or "unknown"

        service_day = st.get("serviceDay", current_time)
        sched_sec = st.get("scheduledDeparture", 0)
        real_sec = st.get("realtimeDeparture", sched_sec)

        aimed_iso = arrow.get(service_day + sched_sec).isoformat()
        expected_iso = arrow.get(service_day + real_sec).isoformat()

        departures.append(
            DepartureData(
                line_code=line_code,
                transport_mode=mode,
                destination=dest,
                aimed_iso=aimed_iso,
                expected_iso=expected_iso,
                is_realtime=bool(st.get("realtime")),
            )
        )
    return departures


def _extract_digitransit_stop_data(data: dict[str, Any]) -> dict[str, Any] | None:
    """Finds first available stop or station record in Digitransit response data."""
    return (
        data.get("stop1")
        or data.get("station1")
        or data.get("stop2")
        or data.get("station2")
    )


class DigitransitTransitProvider(TransitProvider):
    """Transit provider for Finnish public transit via Digitransit GraphQL API (HSL or National)."""

    def __init__(
        self,
        api_url: str = DIGITRANSIT_HSL_URL,
        provider_id: TransitProviderKey | str = "digitransit_hsl",
    ):
        self.api_url = api_url
        self._provider_id = provider_id

    @property
    def provider_id(self) -> TransitProviderKey | str:
        return self._provider_id

    def fetch_stop(
        self,
        session: requests.Session,
        clean_id: str,
        time_range_seconds: int,
        departures_count: int,
        app_config: dict[str, Any],
    ) -> NormalizedStopData:
        raw_id = clean_id.strip()
        raw_lower = raw_id.lower()
        if raw_lower.startswith("nysse:"):
            bare = raw_id[6:].strip()
            id1 = f"tampere:{bare}"
            id2 = raw_id
        elif ":" in raw_id and not raw_lower.startswith("hsl:"):
            id1 = raw_id
            id2 = raw_id
        else:
            bare_id = raw_id[4:].strip() if raw_lower.startswith("hsl:") else raw_id
            id1 = bare_id
            id2 = f"HSL:{bare_id}"

        raw_template = """
        query GetDepartures($id1: String!, $id2: String!, $n: Int!, $t: Int!) {
          stop1: stop(id: $id1) { ...StopFields }
          station1: station(id: $id1) { ...StopFields }
          stop2: stop(id: $id2) { ...StopFields }
          station2: station(id: $id2) { ...StopFields }
        }
        fragment StopFields on Stop {
          name
          lat
          lon
          stoptimesWithoutPatterns(numberOfDepartures: $n, timeRange: $t) {
            scheduledDeparture
            realtimeDeparture
            realtime
            serviceDay
            headsign
            trip {
              route {
                shortName
                mode
              }
            }
          }
        }
        """
        variables = {
            "id1": id1,
            "id2": id2,
            "n": departures_count,
            "t": time_range_seconds,
        }

        sub_key = app_config.get("DIGITRANSIT_SUBSCRIPTION_KEY")
        if not sub_key or not str(sub_key).strip():
            raise ConfigError(
                "Missing required config 'DIGITRANSIT_SUBSCRIPTION_KEY' in .env.\n"
                "Digitransit requires an API subscription key for all requests.\n"
                "Register for a free key at: https://digitransit.fi/en/developers/api-registration/"
            )

        headers = {
            "digitransit-subscription-key": str(sub_key).strip(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        res = session.post(
            self.api_url,
            json={
                "query": textwrap.dedent(raw_template).strip(),
                "variables": variables,
            },
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if res.status_code in {401, 403}:
            raise ConfigError("Invalid or unauthorized 'DIGITRANSIT_SUBSCRIPTION_KEY'.")
        if res.status_code == 404:
            raise LookupError(f"Stop ID '{clean_id}' not found on Digitransit.")
        res.raise_for_status()

        body = res.json()
        if "errors" in body:
            raise ValueError(f"GraphQL errors: {body['errors']}")

        stop_data = _extract_digitransit_stop_data(body.get("data", {}))
        if not stop_data:
            raise LookupError(
                f"Stop ID '{clean_id}' returned no stop or station data from Digitransit."
            )

        departures = _parse_digitransit_stoptimes(
            stop_data.get("stoptimesWithoutPatterns", [])
        )
        lat = stop_data.get("lat")
        lon = stop_data.get("lon")
        return NormalizedStopData(
            name=stop_data.get("name") or clean_id,
            latitude=float(lat) if lat is not None else None,
            longitude=float(lon) if lon is not None else None,
            departures=departures,
        )


default_digitransit_hsl_provider = DigitransitTransitProvider(
    api_url=DIGITRANSIT_HSL_URL, provider_id="digitransit_hsl"
)
default_digitransit_finland_provider = DigitransitTransitProvider(
    api_url=DIGITRANSIT_FINLAND_URL, provider_id="digitransit_finland"
)


def fetch_digitransit_stop(
    session: requests.Session,
    clean_id: str,
    time_range_seconds: int,
    departures_count: int,
    app_config: dict[str, Any],
    api_url: str = DIGITRANSIT_HSL_URL,
) -> NormalizedStopData:
    """Convenience function calling DigitransitTransitProvider.fetch_stop."""
    provider = DigitransitTransitProvider(api_url=api_url)
    return provider.fetch_stop(
        session, clean_id, time_range_seconds, departures_count, app_config
    )
