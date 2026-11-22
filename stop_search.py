"""CLI utility to search for stop IDs in Finland (Digitransit) and Sweden (ResRobot)."""

import argparse
import os
import sys

import dotenv
import requests

from adapters.digitransit import search_digitransit_stops
from adapters.resrobot import search_resrobot_stops
from config import ConfigError, load_app_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Search transit stop IDs for stoppesteder.txt."
    )
    parser.add_argument("query", help="Stop name to search for (e.g. 'T-Centralen').")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--fi",
        action="store_true",
        help="Search Finland (Digitransit; platform-level IDs with sample destinations). Use the destination and your local knowledge to infer the direction.",
    )
    group.add_argument(
        "--se",
        action="store_true",
        help="Search Sweden (ResRobot; whole-station 74xxxxxxx IDs covering all directions).",
    )
    parser.add_argument("--city", help="Filter results by city/feed (e.g. 'kuopio', 'helsinki', 'stockholm').")
    parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10).")
    args = parser.parse_args(argv)

    dotenv.load_dotenv()
    app_config = {**os.environ, **load_app_settings()}
    session = requests.Session()

    try:
        if args.fi:
            results = search_digitransit_stops(session, args.query, app_config, limit=args.limit, city=args.city)
        else:
            results = search_resrobot_stops(session, args.query, app_config, limit=args.limit, city=args.city)
    except (ConfigError, requests.RequestException) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not results:
        print(f"No stops found for '{args.query}'.")
        return 0

    for name, stop_id in results:
        print(f'{name} = "{stop_id}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
