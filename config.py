import logging
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from i18n import translate_international_message


class ConfigError(Exception):
    """Raised when configuration (.env or settings) is missing or invalid."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class TerminalStyle:
    MODERN = "modern"
    FANCY = "fancy"
    CLASSIC = "classic"


# Default fallback values (can be overridden by config.toml)
DEFAULT_DESTINATION_MAX_WIDTH = 28
DEFAULT_TRANSPORT_MODE_MAX_WIDTH = 7
DEFAULT_TRANSIT_NAMING_STYLE = "cultural"
DEFAULT_TIME_RANGE_SECONDS = 5400  # 90 minutes
DEFAULT_DEPARTURES_COUNT = 10
DEFAULT_REFRESH_INTERVAL_SECONDS = 60
DEFAULT_TERMINAL_WIDTH = 95
DEFAULT_USE_NORMALIZED_STOP_NAMES = True

REQUEST_TIMEOUT_SECONDS = 10
WEATHER_CACHE_DURATION_SECONDS = 1800  # 30 minutes cache for weather
DEFAULT_MAX_CONSECUTIVE_FAILURES = 10

ENTUR_GRAPHQL_URL = "https://api.entur.io/journey-planner/v3/graphql"
DIGITRANSIT_HSL_URL = "https://api.digitransit.fi/routing/v2/hsl/gtfs/v1"
DIGITRANSIT_FINLAND_URL = "https://api.digitransit.fi/routing/v2/finland/gtfs/v1"


def get_xdg_config_dir() -> Path:
    """Returns ~/.config/avgangstider or $XDG_CONFIG_HOME/avgangstider."""
    base = (
        Path(xdg)
        if (xdg := os.environ.get("XDG_CONFIG_HOME"))
        else Path.home() / ".config"
    )
    return base / "avgangstider"


def get_xdg_cache_dir() -> Path:
    """Returns ~/.cache/avgangstider or $XDG_CACHE_HOME/avgangstider."""
    base = (
        Path(xdg)
        if (xdg := os.environ.get("XDG_CACHE_HOME"))
        else Path.home() / ".cache"
    )
    path = base / "avgangstider"
    path.mkdir(parents=True, exist_ok=True)
    return path


CACHE_DIR = get_xdg_cache_dir()
WEATHER_CACHE_FILE = CACHE_DIR / "weather_cache.json"
LOG_FILE = CACHE_DIR / "avgangstider.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)

from models import StopProfile

logger = logging.getLogger("avgangstider.config")


def load_app_settings(config_toml_path: Path | None = None) -> dict[str, Any]:
    """
    Loads non-secret settings from config.toml with fallback to built-in defaults.
    Searches in:
    1. Specified config_toml_path
    2. Current working directory ./config.toml
    3. User config directory ~/.config/avgangstider/config.toml
    4. Project directory containing this file
    """
    candidates = []
    if config_toml_path:
        candidates.append(Path(config_toml_path))
    else:
        candidates.extend(
            [
                Path.cwd() / "config.toml",
                get_xdg_config_dir() / "config.toml",
                Path(__file__).resolve().parent / "config.toml",
            ]
        )

    loaded_toml = {}
    for candidate in candidates:
        if candidate.is_file():
            try:
                with open(candidate, "rb") as f:
                    loaded_toml = tomllib.load(f)
                break
            except (OSError, tomllib.TOMLDecodeError) as e:
                logger.warning("Failed to parse config.toml at %s: %s", candidate, e)

    display = loaded_toml.get("display", {})
    query = loaded_toml.get("query", {})
    cache = loaded_toml.get("cache", {})
    network = loaded_toml.get("network", {})

    mode_ov = display.get("mode_overrides", {})
    sys_ov = display.get("system_overrides", {})

    return {
        "destination_max_width": int(
            display.get("destination_max_width", DEFAULT_DESTINATION_MAX_WIDTH)
        ),
        "transport_mode_max_width": int(
            display.get("transport_mode_max_width", DEFAULT_TRANSPORT_MODE_MAX_WIDTH)
        ),
        "transit_naming_style": str(
            display.get("transit_naming_style", DEFAULT_TRANSIT_NAMING_STYLE)
        ),
        "mode_overrides": {str(k).lower(): str(v) for k, v in mode_ov.items()}
        if isinstance(mode_ov, dict)
        else {},
        "system_overrides": {str(k).lower(): str(v) for k, v in sys_ov.items()}
        if isinstance(sys_ov, dict)
        else {},
        "terminal_width": int(display.get("terminal_width", DEFAULT_TERMINAL_WIDTH)),
        "terminal_style": str(display.get("terminal_style", TerminalStyle.MODERN)),
        "language": display.get("language"),
        "use_normalized_stop_names": bool(
            display.get("use_normalized_stop_names", DEFAULT_USE_NORMALIZED_STOP_NAMES)
        ),
        "time_range_seconds": int(
            query.get("time_range_seconds", DEFAULT_TIME_RANGE_SECONDS)
        ),
        "departures_count": int(
            query.get("departures_count", DEFAULT_DEPARTURES_COUNT)
        ),
        "refresh_interval_seconds": int(
            query.get("refresh_interval_seconds", DEFAULT_REFRESH_INTERVAL_SECONDS)
        ),
        "weather_cache_duration_seconds": int(
            cache.get("weather_cache_duration_seconds", WEATHER_CACHE_DURATION_SECONDS)
        ),
        "request_timeout_seconds": int(
            network.get("request_timeout_seconds", REQUEST_TIMEOUT_SECONDS)
        ),
        "max_consecutive_failures": int(
            network.get("max_consecutive_failures", DEFAULT_MAX_CONSECUTIVE_FAILURES)
        ),
    }


# Initial settings loaded from config.toml (or defaults)
APP_SETTINGS = load_app_settings()

DESTINATION_MAX_WIDTH = APP_SETTINGS["destination_max_width"]
TRANSPORT_MODE_MAX_WIDTH = APP_SETTINGS["transport_mode_max_width"]
DEFAULT_TRANSIT_NAMING_STYLE = APP_SETTINGS["transit_naming_style"]
MODE_OVERRIDES = APP_SETTINGS["mode_overrides"]
SYSTEM_OVERRIDES = APP_SETTINGS["system_overrides"]
DEFAULT_TERMINAL_WIDTH = APP_SETTINGS["terminal_width"]
DEFAULT_TIME_RANGE_SECONDS = APP_SETTINGS["time_range_seconds"]
DEFAULT_DEPARTURES_COUNT = APP_SETTINGS["departures_count"]
DEFAULT_REFRESH_INTERVAL_SECONDS = APP_SETTINGS["refresh_interval_seconds"]
REQUEST_TIMEOUT_SECONDS = APP_SETTINGS["request_timeout_seconds"]
WEATHER_CACHE_DURATION_SECONDS = APP_SETTINGS["weather_cache_duration_seconds"]
DEFAULT_USE_NORMALIZED_STOP_NAMES = APP_SETTINGS["use_normalized_stop_names"]


def _is_local_dev_workspace(cwd: Path) -> bool:
    """Checks if cwd contains our development pyproject.toml."""
    pyproject = cwd / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        content = pyproject.read_text(encoding="utf-8")
        return 'name = "avgangstider-entur-python"' in content
    except Exception:
        print("error when looking for config file")
        raise


def _resolve_fallback_file(custom: str | None, xdg_path: Path, cwd_path: Path) -> Path:
    """Helper to resolve a specific file from custom CLI flag, XDG, or cwd."""
    if custom:
        return Path(custom)
    return xdg_path if xdg_path.is_file() else cwd_path


def resolve_config_and_stops_files(
    custom_env: str | None = None, custom_stops: str | None = None
) -> tuple[Path, Path]:
    """
    Resolves (.env, stoppesteder.txt) following precedence:
    1. CLI overrides (--config, --stops) if provided.
    2. Local project directory IF current working directory contains our pyproject.toml.
    3. User global XDG configuration directory (~/.config/avgangstider/).
    4. Directory of script.
    """
    if custom_env and custom_stops:
        return Path(custom_env), Path(custom_stops)

    cwd = Path.cwd()
    if (
        _is_local_dev_workspace(cwd)
        and (cwd / ".env").is_file()
        and (cwd / "stoppesteder.txt").is_file()
    ):
        env_file = Path(custom_env) if custom_env else cwd / ".env"
        stops_file = Path(custom_stops) if custom_stops else cwd / "stoppesteder.txt"
        return env_file, stops_file

    xdg_dir = get_xdg_config_dir()
    env_file = _resolve_fallback_file(custom_env, xdg_dir / ".env", cwd / ".env")
    stops_file = _resolve_fallback_file(
        custom_stops, xdg_dir / "stoppesteder.txt", cwd / "stoppesteder.txt"
    )
    return env_file, stops_file


def _handle_missing_stops_file(file_path: Path, lang: str | None) -> None:
    """Displays user-friendly guidance when stoppesteder.txt is missing, then exits."""
    print(
        translate_international_message("err_no_stops_file", lang=lang, path=file_path)
    )
    print(translate_international_message("create_stops_file", lang=lang))
    print(translate_international_message("see_example_file", lang=lang))
    print(translate_international_message("find_stops_url", lang=lang))
    sys.exit(1)


def _parse_profile_header(
    header_content: str,
) -> tuple[str, bool | None, str | None, dict[str, str]] | None:
    """Parses profile section header, returning (profile_name, use_norm_opt, transit_naming_opt, options_dict)."""
    parts = [p.strip() for p in header_content.split(",")]
    profile_name = parts[0].strip().lower()
    if not profile_name:
        return None

    use_norm_opt: bool | None = None
    transit_naming_opt: str | None = None
    options_dict: dict[str, str] = {}

    for opt in parts[1:]:
        if "=" in opt:
            opt_key, opt_val = opt.split("=", 1)
            opt_key = opt_key.strip().lower()
            opt_val = opt_val.strip().lower()
            options_dict[opt_key] = opt_val
            if opt_key in ("use_normalized_names", "use_normalized_stop_names"):
                use_norm_opt = opt_val in ("true", "1", "yes")
            elif opt_key in ("transit_naming", "transit_naming_style"):
                transit_naming_opt = opt_val

    return profile_name, use_norm_opt, transit_naming_opt, options_dict


def _update_or_create_profile(
    profiles: dict[str, StopProfile],
    profile_name: str,
    use_norm_opt: bool | None,
    transit_naming_opt: str | None,
    options_dict: dict[str, str],
) -> None:
    """Updates existing StopProfile or adds a new one to profiles dict."""
    if profile_name not in profiles:
        profiles[profile_name] = StopProfile(
            name=profile_name,
            stops={},
            use_normalized_names=use_norm_opt,
            transit_naming=transit_naming_opt,
            options=options_dict,
        )
    else:
        if use_norm_opt is not None:
            profiles[profile_name].use_normalized_names = use_norm_opt
        if transit_naming_opt is not None:
            profiles[profile_name].transit_naming = transit_naming_opt
        profiles[profile_name].options.update(options_dict)


def _parse_stop_entry(line: str) -> tuple[str, str] | None:
    """Parses 'name = id' line into cleaned (name, id) tuple."""
    if "=" not in line:
        return None
    name, nsr_id = line.split("=", 1)
    return name.strip().strip('"').strip("'"), nsr_id.strip().strip('"').strip("'")


def _process_header_line(
    line: str,
    line_no: int,
    file_path: Path,
    lang: str | None,
    profiles: dict[str, StopProfile],
) -> str:
    """Validates and processes a section header line, returning active profile name."""
    header_content = line[1:-1].strip()
    parsed = _parse_profile_header(header_content) if header_content else None
    if not parsed:
        print(
            translate_international_message(
                "err_empty_section", lang=lang, line=line_no, path=file_path
            )
        )
        sys.exit(1)
    profile_name, use_norm, transit_naming, options = parsed
    _update_or_create_profile(profiles, profile_name, use_norm, transit_naming, options)
    return profile_name


def load_stop_places(
    file_path: Path, lang: str | None = None
) -> dict[str, StopProfile]:
    """
    Reads stop places grouped by sections ([home], [work], etc.) from file.
    Supports per-profile configuration options in section header, e.g.:
    [home, use_normalized_names=false]

    Returns: {'home': StopProfile(name='home', stops={...}, use_normalized_names=False), ...}
    """
    if not file_path.is_file():
        _handle_missing_stops_file(file_path, lang)

    profiles: dict[str, StopProfile] = {}
    active_profile_name: str | None = None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if line.startswith("[") and line.endswith("]"):
                    active_profile_name = _process_header_line(
                        line, line_no, file_path, lang, profiles
                    )
                    continue

                if "=" not in line:
                    continue

                if active_profile_name is None:
                    print(
                        translate_international_message(
                            "err_no_section_header", lang=lang, path=file_path
                        )
                    )
                    print(
                        translate_international_message(
                            "line_missing_header", lang=lang, line=line_no, text=line
                        )
                    )
                    sys.exit(1)

                if entry := _parse_stop_entry(line):
                    clean_name, clean_id = entry
                    profiles[active_profile_name].stops[clean_name] = clean_id

        if not profiles:
            print(
                translate_international_message(
                    "err_no_profiles_found", lang=lang, path=file_path
                )
            )
            print(translate_international_message("define_at_least_one", lang=lang))
            print('[home]\nKlimavegen = "NSR:StopPlace:53434"')
            sys.exit(1)

        return profiles
    except OSError as e:
        logger.error("Failed to read stop places file: %s", e)
        print(
            translate_international_message(
                "err_reading_file", lang=lang, path=file_path, err=e
            )
        )
        sys.exit(1)
