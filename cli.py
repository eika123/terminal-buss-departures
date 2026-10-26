import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import dotenv_values

from adapters import fetch_and_update_departures, resolve_stop_place_provider
from config import (
    DEFAULT_DEPARTURES_COUNT,
    DEFAULT_REFRESH_INTERVAL_SECONDS,
    DEFAULT_TERMINAL_WIDTH,
    DEFAULT_TIME_RANGE_SECONDS,
    DEFAULT_TRANSIT_NAMING_STYLE,
    DEFAULT_USE_NORMALIZED_STOP_NAMES,
    MODE_OVERRIDES,
    SYSTEM_OVERRIDES,
    TRANSPORT_MODE_MAX_WIDTH,
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
    except (subprocess.SubprocessError, FileNotFoundError):
        # Fallback to ANSI clear if terminal is non-interactive or clear binary missing
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


def parse_arguments(
    all_profiles: dict[str, StopProfile] | None = None,
    argv: list[str] | None = None,
) -> argparse.Namespace:
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
        help=f"Lookahead window in seconds (default: {DEFAULT_TIME_RANGE_SECONDS}s = {DEFAULT_TIME_RANGE_SECONDS // 60}m)",
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

    return parser.parse_args(argv)


def _extract_flag_value(argv: list[str], flag: str) -> str | None:
    """Finds argument value for --flag or --flag=value."""
    for i, arg in enumerate(argv):
        if arg == flag and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith(f"{flag}="):
            return arg.split("=", 1)[1]
    return None


def _parse_early_cli_options(
    argv: list[str],
) -> tuple[str | None, str | None, str | None]:
    """Extracts custom config, stops, and language before full argparse execution."""
    custom_env = _extract_flag_value(argv, "--config")
    custom_stops = _extract_flag_value(argv, "--stops")
    raw_lang = _extract_flag_value(argv, "--lang")
    cli_lang = raw_lang if raw_lang in TRANSLATIONS else None
    return custom_env, custom_stops, cli_lang


def _resolve_active_language(cli_lang: str | None, env_path: Path) -> str:
    """Resolves active language based on early CLI flag or preliminary .env."""
    prelim_config = dotenv_values(env_path) if env_path.is_file() else {}
    lang = cli_lang or prelim_config.get("LANGUAGE") or DEFAULT_LANGUAGE
    return lang if lang in TRANSLATIONS else DEFAULT_LANGUAGE


def _ensure_config_file(env_path: Path, active_lang: str) -> None:
    """Verifies that .env configuration file exists, or prints help and exits."""
    if not env_path.is_file():
        print(
            translate_international_message(
                "err_no_env", lang=active_lang, path=env_path
            )
        )
        print(translate_international_message("create_env_file", lang=active_lang))
        print(f"Place it in {get_xdg_config_dir() / '.env'} or project root.")
        sys.exit(1)


def _select_active_profile(
    all_profiles: dict[str, StopProfile],
    args: argparse.Namespace,
    active_lang: str,
) -> StopProfile:
    """Resolves which profile/section to display."""
    chosen = args.profile or (
        args.positional_profile.lower() if args.positional_profile else None
    )
    if chosen:
        if chosen not in all_profiles:
            available = ", ".join(f"'{p}'" for p in all_profiles)
            print(
                translate_international_message(
                    "err_profile_not_found", lang=active_lang, profile=chosen
                )
            )
            print(
                translate_international_message(
                    "available_profiles", lang=active_lang, profiles=available
                )
            )
            sys.exit(1)
        active_profile = all_profiles[chosen]
    else:
        first_profile_name = next(iter(all_profiles.keys()))
        active_profile = all_profiles[first_profile_name]

    if not active_profile.stops:
        print(translate_international_message("err_no_stops_active", lang=active_lang))
        sys.exit(1)
    return active_profile


def _initialize_stops_state(stops: dict[str, str]) -> dict[str, StopPlaceState]:
    """Creates StopPlaceState mapping for each stop place with detected provider."""
    stops_state: dict[str, StopPlaceState] = {}
    for name, raw_id in stops.items():
        prov, clean_id = resolve_stop_place_provider(raw_id)
        stops_state[name] = StopPlaceState(
            name=name,
            raw_id=raw_id,
            clean_id=clean_id,
            provider=prov,
        )
    return stops_state


def _resolve_display_preferences(
    active_profile: StopProfile,
    app_config: dict[str, Any],
) -> tuple[bool, str]:
    """Determines normalized stop names flag and transit naming style with precedence."""
    if active_profile.use_normalized_names is not None:
        use_normalized_names = active_profile.use_normalized_names
    else:
        use_norm = app_config.get("use_normalized_stop_names")
        use_normalized_names = (
            use_norm.lower() in ("true", "1", "yes")
            if isinstance(use_norm, str)
            else bool(use_norm)
            if use_norm is not None
            else DEFAULT_USE_NORMALIZED_STOP_NAMES
        )

    if active_profile.transit_naming is not None:
        transit_naming_style = active_profile.transit_naming
    else:
        transit_naming_style = str(
            app_config.get("transit_naming_style", DEFAULT_TRANSIT_NAMING_STYLE)
        )

    return use_normalized_names, transit_naming_style


def _run_display_loop(
    session: requests.Session,
    stops_state: dict[str, StopPlaceState],
    stop_presenter: StopPlacePresenter,
    args: argparse.Namespace,
    app_config: dict[str, Any],
    active_lang: str,
) -> None:
    """Executes the recurring departure refresh and terminal rendering loop."""
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


def main() -> None:
    custom_env, custom_stops, cli_lang = _parse_early_cli_options(sys.argv)
    env_path, stops_path = resolve_config_and_stops_files(custom_env, custom_stops)
    active_lang = _resolve_active_language(cli_lang, env_path)

    _ensure_config_file(env_path, active_lang)
    app_config = dotenv_values(env_path)

    all_profiles = load_stop_places(stops_path, lang=active_lang)
    args = parse_arguments(all_profiles)
    if args.lang and args.lang in TRANSLATIONS:
        active_lang = args.lang

    active_profile = _select_active_profile(all_profiles, args, active_lang)
    stops_state = _initialize_stops_state(active_profile.stops)
    session = create_resilient_session(retries=3, backoff_factor=0.5)
    clear_terminal()

    use_norm, transit_naming = _resolve_display_preferences(active_profile, app_config)
    stop_presenter = StopPlacePresenter(
        lang=active_lang,
        style=TerminalStyle.MODERN,
        terminal_width=DEFAULT_TERMINAL_WIDTH,
        use_normalized_stop_names=use_norm,
        transport_mode_max_width=TRANSPORT_MODE_MAX_WIDTH,
        transit_naming_style=transit_naming,
        mode_overrides=MODE_OVERRIDES,
        system_overrides=SYSTEM_OVERRIDES,
    )

    _run_display_loop(
        session, stops_state, stop_presenter, args, app_config, active_lang
    )


if __name__ == "__main__":
    main()
