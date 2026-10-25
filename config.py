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
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "avgangstider"
    return Path.home() / ".config" / "avgangstider"


def get_xdg_cache_dir() -> Path:
    """Returns ~/.cache/avgangstider or $XDG_CACHE_HOME/avgangstider."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        path = Path(xdg) / "avgangstider"
    else:
        path = Path.home() / ".cache" / "avgangstider"
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
        candidates.append(Path.cwd() / "config.toml")
        candidates.append(get_xdg_config_dir() / "config.toml")
        candidates.append(Path(__file__).resolve().parent / "config.toml")

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

    return {
        "destination_max_width": int(display.get("destination_max_width", DEFAULT_DESTINATION_MAX_WIDTH)),
        "terminal_width": int(display.get("terminal_width", DEFAULT_TERMINAL_WIDTH)),
        "terminal_style": str(display.get("terminal_style", TerminalStyle.MODERN)),
        "language": display.get("language"),
        "use_normalized_stop_names": bool(display.get("use_normalized_stop_names", DEFAULT_USE_NORMALIZED_STOP_NAMES)),
        "time_range_seconds": int(query.get("time_range_seconds", DEFAULT_TIME_RANGE_SECONDS)),
        "departures_count": int(query.get("departures_count", DEFAULT_DEPARTURES_COUNT)),
        "refresh_interval_seconds": int(query.get("refresh_interval_seconds", DEFAULT_REFRESH_INTERVAL_SECONDS)),
        "weather_cache_duration_seconds": int(cache.get("weather_cache_duration_seconds", WEATHER_CACHE_DURATION_SECONDS)),
        "request_timeout_seconds": int(network.get("request_timeout_seconds", REQUEST_TIMEOUT_SECONDS)),
        "max_consecutive_failures": int(network.get("max_consecutive_failures", DEFAULT_MAX_CONSECUTIVE_FAILURES)),
    }


# Initial settings loaded from config.toml (or defaults)
APP_SETTINGS = load_app_settings()

DESTINATION_MAX_WIDTH = APP_SETTINGS["destination_max_width"]
DEFAULT_TERMINAL_WIDTH = APP_SETTINGS["terminal_width"]
DEFAULT_TIME_RANGE_SECONDS = APP_SETTINGS["time_range_seconds"]
DEFAULT_DEPARTURES_COUNT = APP_SETTINGS["departures_count"]
DEFAULT_REFRESH_INTERVAL_SECONDS = APP_SETTINGS["refresh_interval_seconds"]
REQUEST_TIMEOUT_SECONDS = APP_SETTINGS["request_timeout_seconds"]
WEATHER_CACHE_DURATION_SECONDS = APP_SETTINGS["weather_cache_duration_seconds"]
DEFAULT_USE_NORMALIZED_STOP_NAMES = APP_SETTINGS["use_normalized_stop_names"]


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
    pyproject = cwd / "pyproject.toml"
    is_local_dev = False
    if pyproject.is_file():
        try:
            content = pyproject.read_text(encoding="utf-8")
            if 'name = "avgangstider-entur-python"' in content:
                is_local_dev = True
        except Exception:
            print("error when looking for config file")
            raise

    if is_local_dev and (cwd / ".env").is_file() and (cwd / "stoppesteder.txt").is_file():
        env_file = Path(custom_env) if custom_env else cwd / ".env"
        stops_file = Path(custom_stops) if custom_stops else cwd / "stoppesteder.txt"
        return env_file, stops_file

    xdg_dir = get_xdg_config_dir()
    xdg_env = xdg_dir / ".env"
    xdg_stops = xdg_dir / "stoppesteder.txt"

    env_file = Path(custom_env) if custom_env else (xdg_env if xdg_env.is_file() else cwd / ".env")
    stops_file = Path(custom_stops) if custom_stops else (xdg_stops if xdg_stops.is_file() else cwd / "stoppesteder.txt")

    return env_file, stops_file


def load_stop_places(file_path: Path, lang: str | None = None) -> dict[str, dict[str, str]]:
    """
    Reads stop places grouped by sections ([home], [work], etc.) from file.
    Returns: {'home': {'Stop1': 'ID1', ...}, 'work': {...}}
    """
    if not file_path.is_file():
        print(translate_international_message("err_no_stops_file", lang=lang, path=file_path))
        print(translate_international_message("create_stops_file", lang=lang))
        print(translate_international_message("see_example_file", lang=lang))
        print(translate_international_message("find_stops_url", lang=lang))
        sys.exit(1)

    profiles: dict[str, dict[str, str]] = {}
    active_profile: str | None = None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                if line.startswith("[") and line.endswith("]"):
                    active_profile = line[1:-1].strip().lower()
                    if not active_profile:
                        print(translate_international_message("err_empty_section", lang=lang, line=line_no, path=file_path))
                        sys.exit(1)
                    if active_profile not in profiles:
                        profiles[active_profile] = {}
                    continue

                if "=" not in line:
                    continue

                if active_profile is None:
                    print(translate_international_message("err_no_section_header", lang=lang, path=file_path))
                    print(translate_international_message("line_missing_header", lang=lang, line=line_no, text=line))
                    sys.exit(1)

                name, nsr_id = line.split("=", 1)
                clean_name = name.strip().strip('"').strip("'")
                clean_id = nsr_id.strip().strip('"').strip("'")

                profiles[active_profile][clean_name] = clean_id

        if not profiles:
            print(translate_international_message("err_no_profiles_found", lang=lang, path=file_path))
            print(translate_international_message("define_at_least_one", lang=lang))
            print('[home]\nKlimavegen = "NSR:StopPlace:53434"')
            sys.exit(1)

        return profiles
    except OSError as e:
        logger.error("Failed to read stop places file: %s", e)
        print(translate_international_message("err_reading_file", lang=lang, path=file_path, err=e))
        sys.exit(1)

