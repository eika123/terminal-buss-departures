import textwrap
from string import Template
from typing import Any

import requests

from config import ENTUR_GRAPHQL_URL, REQUEST_TIMEOUT_SECONDS, ConfigError
from models import DepartureData, NormalizedStopData, TransitProvider

ENTUR_MODE_MAP: dict[str, str] = {
    "coach": "bus",
    "tram": "tram",
    "rail": "rail",
    "metro": "metro",
    "water": "ferry",
    "air": "air",
}


def _parse_entur_calls(calls: list[dict[str, Any]]) -> list[DepartureData]:
    """Extracts DepartureData items from Entur estimatedCalls."""
    departures: list[DepartureData] = []
    for call in calls:
        journey = call.get("serviceJourney", {})
        pattern = journey.get("journeyPattern", {})
        line = pattern.get("line", {})
        line_code = line.get("publicCode") or "?"
        raw_mode = (line.get("transportMode") or "bus").lower()
        mode = ENTUR_MODE_MAP.get(raw_mode, "bus")
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
    return departures


class EnturTransitProvider(TransitProvider):
    """Transit provider for Norwegian public transit via Entur's JourneyPlanner GraphQL API."""

    def __init__(self, api_url: str = ENTUR_GRAPHQL_URL):
        self.api_url = api_url

    @property
    def provider_id(self) -> str:
        return "entur"

    def fetch_stop(
        self,
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
        if not client_name or not str(client_name).strip():
            raise ConfigError(
                "Missing required config 'ET_CLIENT_NAME' in .env.\n"
                "Entur requires all API consumers to identify themselves via the ET-Client-Name header.\n"
                "Format: <company>-<application> (e.g. 'mycompany-avgangstider')."
            )

        headers = {
            "ET-Client-Name": str(client_name).strip(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        res = session.post(
            self.api_url,
            json={"query": query},
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if res.status_code == 404:
            raise LookupError(f"Stop ID '{clean_id}' not found on Entur.")
        res.raise_for_status()

        body = res.json()
        if "errors" in body:
            raise ValueError(f"GraphQL errors: {body['errors']}")

        stop_place = body.get("data", {}).get("stopPlace")
        if not stop_place:
            raise LookupError(f"Stop ID '{clean_id}' returned no stopPlace data from Entur.")

        departures = _parse_entur_calls(stop_place.get("estimatedCalls", []))
        lat = stop_place.get("latitude")
        lon = stop_place.get("longitude")
        return NormalizedStopData(
            name=stop_place.get("name") or clean_id,
            latitude=float(lat) if lat is not None else None,
            longitude=float(lon) if lon is not None else None,
            departures=departures,
        )


default_entur_provider = EnturTransitProvider()


def fetch_entur_stop(
    session: requests.Session,
    clean_id: str,
    time_range_seconds: int,
    departures_count: int,
    app_config: dict[str, Any],
) -> NormalizedStopData:
    """Convenience function calling default_entur_provider.fetch_stop."""
    return default_entur_provider.fetch_stop(
        session, clean_id, time_range_seconds, departures_count, app_config
    )
