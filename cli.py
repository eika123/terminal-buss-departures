import argparse
import subprocess
import sys
import time

from dotenv import dotenv_values

from adapters import fetch_and_update_departures, resolve_stop_place_provider
from config import (
    DEFAULT_DEPARTURES_COUNT,
    DEFAULT_REFRESH_INTERVAL_SECONDS,
    DEFAULT_TERMINAL_WIDTH,
    DEFAULT_TIME_RANGE_SECONDS,
    DEFAULT_USE_NORMALIZED_STOP_NAMES,
    TerminalStyle,
    get_xdg_config_dir,
    load_stop_places,
    resolve_config_and_stops_files,
)
from i18n import DEFAULT_LANGUAGE, TRANSLATIONS, translate_international_message
from models import StopPlaceState, StopProfile
from presenters import StopPlacePresenter
from resilience import MaxConsecutiveFailuresExceeded, create_resilient_session


def clear_terminal() -> None:
    command = "cls" if sys.platform.startswith("win") else "clear"
    try:
        # B603 looks for command injections -- we always know what contains.
        subprocess.run([command], check=True)  # nosec B603
    except Exception:
        print("Unexpected error while clearing terminal")
        raise


def parse_arguments(all_profiles: dict[str, StopProfile] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Nordic transit departure board with live weather forecast.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    if all_profiles:
        group = parser.add_mutually_exclusive_group()
        for index, profile_name in enumerate(all_profiles.keys()):
            help_text = f"Show stops for section '{profile_name}'"
            if index == 0:
                help_text += " (default)"
            group.add_argument(
                f"--{profile_name}",
                dest="profile",
                action="store_const",
                const=profile_name,
                help=help_text,
            )

    parser.add_argument(
        "positional_profile",
        nargs="?",
        default=None,
        help="Optional section/profile name (e.g. 'home' or 'work')",
    )

    parser.add_argument(
        "--config",
        dest="custom_config",
        default=None,
        help="Path to custom .env configuration file (default: ~/.config/avgangstider/.env or ./.env)",
    )

    parser.add_argument(
        "--stops",
        dest="custom_stops",
        default=None,
        help="Path to custom stoppesteder.txt file (default: ~/.config/avgangstider/stoppesteder.txt or ./stoppesteder.txt)",
    )

    parser.add_argument(
        "--lang",
        choices=["no", "sv", "fi", "en"],
        default=None,
        help="Display language: 'no' (Norwegian), 'sv' (Swedish), 'fi' (Finnish), 'en' (English).",
    )

    parser.add_argument(
        "--timerange",
        type=int,
        default=DEFAULT_TIME_RANGE_SECONDS,
        help=f"Lookahead window in seconds (default: {DEFAULT_TIME_RANGE_SECONDS}s = {DEFAULT_TIME_RANGE_SECONDS//60}m)",
    )

    parser.add_argument(
        "--antall",
        type=int,
        default=DEFAULT_DEPARTURES_COUNT,
        help=f"Max departures per stop place (default: {DEFAULT_DEPARTURES_COUNT})",
    )

    parser.add_argument(
        "--intervall",
        type=int,
        default=DEFAULT_REFRESH_INTERVAL_SECONDS,
        help=f"Refresh interval in seconds (default: {DEFAULT_REFRESH_INTERVAL_SECONDS}s)",
    )

    return parser.parse_args()


def main() -> None:
    # 1. Early flag parsing to resolve custom config / stops and language
    custom_env = None
    custom_stops = None
    cli_lang = None

    for i, arg in enumerate(sys.argv):
        if arg == "--config" and i + 1 < len(sys.argv):
            custom_env = sys.argv[i + 1]
        elif arg.startswith("--config="):
            custom_env = arg.split("=", 1)[1]
        elif arg == "--stops" and i + 1 < len(sys.argv):
            custom_stops = sys.argv[i + 1]
        elif arg.startswith("--stops="):
            custom_stops = arg.split("=", 1)[1]
        elif arg == "--lang" and i + 1 < len(sys.argv):
            if sys.argv[i + 1] in TRANSLATIONS:
                cli_lang = sys.argv[i + 1]
        elif arg.startswith("--lang="):
            val = arg.split("=", 1)[1]
            if val in TRANSLATIONS:
                cli_lang = val

    env_path, stops_path = resolve_config_and_stops_files(custom_env, custom_stops)

    prelim_config = dotenv_values(env_path) if env_path.is_file() else {}
    active_lang = cli_lang or prelim_config.get("LANGUAGE") or DEFAULT_LANGUAGE
    if active_lang not in TRANSLATIONS:
        active_lang = DEFAULT_LANGUAGE

    # 2. Check configuration file
    if not env_path.is_file():
        print(translate_international_message("err_no_env", lang=active_lang, path=env_path))
        print(translate_international_message("create_env_file", lang=active_lang))
        print(f"Place it in {get_xdg_config_dir() / '.env'} or project root.")
        sys.exit(1)

    app_config = dotenv_values(env_path)

    # 3. Load stop places and parse full CLI arguments
    all_profiles = load_stop_places(stops_path, lang=active_lang)
    args = parse_arguments(all_profiles)

    if args.lang and args.lang in TRANSLATIONS:
        active_lang = args.lang

    # 4. Select active profile
    chosen_profile_name = args.profile or (args.positional_profile.lower() if args.positional_profile else None)

    if chosen_profile_name:
        if chosen_profile_name not in all_profiles:
            available = ", ".join(f"'{p}'" for p in all_profiles)
            print(translate_international_message("err_profile_not_found", lang=active_lang, profile=chosen_profile_name))
            print(translate_international_message("available_profiles", lang=active_lang, profiles=available))
            sys.exit(1)
        active_profile = all_profiles[chosen_profile_name]
    else:
        first_profile_name = next(iter(all_profiles.keys()))
        active_profile = all_profiles[first_profile_name]

    if not active_profile.stops:
        print(translate_international_message("err_no_stops_active", lang=active_lang))
        sys.exit(1)

    # 5. Prepare state per stop place with detected provider
    stops_state: dict[str, StopPlaceState] = {}
    for name, raw_id in active_profile.stops.items():
        prov, clean_id = resolve_stop_place_provider(raw_id)
        stops_state[name] = StopPlaceState(
            name=name,
            raw_id=raw_id,
            clean_id=clean_id,
            provider=prov,
        )

    session = create_resilient_session(retries=3, backoff_factor=0.5)
    clear_terminal()

    # Determine use_normalized_stop_names precedence:
    # 1. Per-profile option in section header ([hjem, use_normalized_names=false])
    # 2. Global app setting from config.toml
    # 3. Built-in default
    if active_profile.use_normalized_names is not None:
        use_normalized_names = active_profile.use_normalized_names
    else:
        use_norm = app_config.get("use_normalized_stop_names")
        use_normalized_names = (
            use_norm.lower() in ("true", "1", "yes")
            if isinstance(use_norm, str)
            else bool(use_norm) if use_norm is not None else DEFAULT_USE_NORMALIZED_STOP_NAMES
        )

    # 6. Initialize presenter
    stop_presenter = StopPlacePresenter(
        lang=active_lang,
        style=TerminalStyle.MODERN,
        terminal_width=DEFAULT_TERMINAL_WIDTH,
        use_normalized_stop_names=use_normalized_names,
    )

    # 7. Main execution loop
    try:
        while True:
            print(translate_international_message("fetching", lang=active_lang))
            fetch_and_update_departures(
                session=session,
                stops_state=stops_state,
                time_range_seconds=args.timerange,
                departures_count=args.antall,
                app_config=app_config,
            )

            clear_terminal()

            for state in stops_state.values():
                stop_presenter.render(state)

            print("=" * (DEFAULT_TERMINAL_WIDTH + 1))
            time.sleep(args.intervall)

    except MaxConsecutiveFailuresExceeded as mcfe:
        print(f"\n{mcfe}")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{translate_international_message('exiting', lang=active_lang)}")
        sys.exit(0)


if __name__ == "__main__":
    main()
