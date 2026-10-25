from string import Template
import textwrap
from typing import Any

import requests

from config import ConfigError, ENTUR_GRAPHQL_URL, REQUEST_TIMEOUT_SECONDS
from models import DepartureData, NormalizedStopData


def fetch_entur_stop(
    session: requests.Session,
    clean_id: str,
    time_range_seconds: int,
    departures_count: int,
    app_config: dict[str, Any],
) -> NormalizedStopData:
    raw_template = """
    {
      stopPlace(id: "$nsr_id") {
        id
        name
        latitude
        longitude
        estimatedCalls(timeRange: $time_range, numberOfDepartures: $num_departures) {
          realtime
          aimedArrivalTime
          aimedDepartureTime
          expectedArrivalTime
          expectedDepartureTime
          destinationDisplay {
            frontText
          }
          serviceJourney {
            journeyPattern {
              line {
                publicCode
                transportMode
              }
            }
          }
        }
      }
    }
    """
    query = Template(textwrap.dedent(raw_template).strip()).substitute(
        nsr_id=clean_id,
        time_range=time_range_seconds,
        num_departures=departures_count,
    )
    client_name = app_config.get("ET_CLIENT_NAME")
    if not client_name:
        raise ConfigError(
            "Missing required config 'ET_CLIENT_NAME' in .env for Entur (Norway).\n"
            "Format: ET_CLIENT_NAME=\"<company>-<application>\""
        )
    headers = {"ET-Client-Name": str(client_name)}
    res = session.post(
        ENTUR_GRAPHQL_URL,
        headers=headers,
        json={"query": query},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if res.status_code != 200:
        raise requests.HTTPError(f"Entur HTTP {res.status_code}: {res.text[:100]}")

    data = res.json()
    if "errors" in data and not data.get("data"):
        raise ValueError("; ".join(e.get("message", "Error") for e in data["errors"]))

    stop_place = data.get("data", {}).get("stopPlace")
    if not stop_place:
        raise ValueError(f"Stop not found in Entur: {clean_id}")

    departures: list[DepartureData] = []
    for call in stop_place.get("estimatedCalls") or []:
        line_info = call.get("serviceJourney", {}).get("journeyPattern", {}).get("line", {})
        line_code = line_info.get("publicCode") or "?"
        mode = line_info.get("transportMode") or "bus"
        dest = call.get("destinationDisplay", {}).get("frontText") or "unknown"

        aimed = call.get("aimedDepartureTime") or call.get("aimedArrivalTime")
        expected = call.get("expectedDepartureTime") or call.get("expectedArrivalTime")
        if not aimed or not expected:
            continue

        departures.append(
            DepartureData(
                line_code=line_code,
                transport_mode=mode,
                destination=dest,
                aimed_iso=aimed,
                expected_iso=expected,
                is_realtime=bool(call.get("realtime")),
            )
        )

    lat = stop_place.get("latitude")
    lon = stop_place.get("longitude")
    return NormalizedStopData(
        name=stop_place.get("name") or clean_id,
        latitude=float(lat) if lat is not None else None,
        longitude=float(lon) if lon is not None else None,
        departures=departures,
    )

