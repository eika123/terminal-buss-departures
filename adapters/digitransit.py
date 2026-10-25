import textwrap
import time
from typing import Any

import arrow
import requests

from config import (
    DIGITRANSIT_HSL_URL,
    REQUEST_TIMEOUT_SECONDS,
    ConfigError,
)
from models import DepartureData, NormalizedStopData


def fetch_digitransit_stop(
    session: requests.Session,
    clean_id: str,
    time_range_seconds: int,
    departures_count: int,
    app_config: dict[str, Any],
    api_url: str = DIGITRANSIT_HSL_URL,
) -> NormalizedStopData:
    raw_id = clean_id.strip()
    bare_id = raw_id[4:].strip() if raw_id.upper().startswith("HSL:") else raw_id
    id_with_prefix = f"HSL:{bare_id}"

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
    headers = {"Content-Type": "application/json"}
    sub_key = app_config.get("DIGITRANSIT_SUBSCRIPTION_KEY") or app_config.get(
        "digitransitSubscriptionKey"
    )
    if not sub_key or not str(sub_key).strip():
        raise ConfigError(
            "Missing required config 'DIGITRANSIT_SUBSCRIPTION_KEY' in .env for Finland (Digitransit).\n"
            "You can register for a free personal API key at:\n"
            "https://digitransit.fi/en/developers/api-registration/"
        )
    headers["digitransit-subscription-key"] = str(sub_key).strip()

    payload = {
        "query": textwrap.dedent(raw_template).strip(),
        "variables": {
            "id1": id_with_prefix,
            "id2": bare_id,
            "n": departures_count,
            "t": time_range_seconds,
        },
    }

    res = session.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if res.status_code != 200:
        raise requests.HTTPError(
            f"Digitransit HTTP {res.status_code}: {res.text[:100]}"
        )

    data = res.json()
    if "errors" in data and not data.get("data"):
        raise ValueError("; ".join(e.get("message", "Error") for e in data["errors"]))

    data_dict = data.get("data") or {}
    stop_data = (
        data_dict.get("stop1")
        or data_dict.get("station1")
        or data_dict.get("stop2")
        or data_dict.get("station2")
    )
    if not stop_data:
        raise LookupError(
            f"Stop not found in Digitransit (tested '{id_with_prefix}' and '{bare_id}')"
        )

    departures: list[DepartureData] = []
    mode_map = {
        "BUS": "bus",
        "TRAM": "tram",
        "RAIL": "rail",
        "SUBWAY": "metro",
        "FERRY": "ferry",
    }

    for st in stop_data.get("stoptimesWithoutPatterns") or []:
        trip = st.get("trip") or {}
        route = trip.get("route") or {}
        line_code = route.get("shortName") or "?"
        raw_mode = (route.get("mode") or "BUS").upper()
        mode = mode_map.get(raw_mode, "bus")
        dest = st.get("headsign") or "unknown"

        service_day = st.get("serviceDay", int(time.time()))
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

    lat = stop_data.get("lat")
    lon = stop_data.get("lon")
    return NormalizedStopData(
        name=stop_data.get("name") or clean_id,
        latitude=float(lat) if lat is not None else None,
        longitude=float(lon) if lon is not None else None,
        departures=departures,
    )
