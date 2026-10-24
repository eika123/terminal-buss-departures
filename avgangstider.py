import argparse
from dataclasses import dataclass
import json
import logging
from pathlib import Path
from string import Template
import subprocess
import sys
import textwrap
import time
from typing import Any

import arrow
from dotenv import dotenv_values
import requests

# ==============================================================================
# CONFIGURATION AND CONSTANTS
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent
ENTUR_GRAPHQL_URL = "https://api.entur.io/journey-planner/v3/graphql"
DIGITRANSIT_HSL_URL = "https://api.digitransit.fi/routing/v2/hsl/gtfs/v1"
DIGITRANSIT_FINLAND_URL = "https://api.digitransit.fi/routing/v2/finland/gtfs/v1"
MET_LOCATIONFORECAST_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
WEATHER_CACHE_FILE = BASE_DIR / ".weather_cache.json"
LOG_FILE = BASE_DIR / "avgangstider.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)

DEFAULT_TIME_RANGE_SECONDS = 5400  # 90 minutes
DEFAULT_DEPARTURES_COUNT = 10
DEFAULT_REFRESH_INTERVAL_SECONDS = 60
DEFAULT_TERMINAL_WIDTH = 95
REQUEST_TIMEOUT_SECONDS = 10
WEATHER_CACHE_DURATION_SECONDS = 1800  # 30 minutes cache for weather

config: dict[str, Any] = {}


class TerminalStyle:
    MODERN = "moderne"
    FANCY = "fancy"
    CLASSIC = "klassisk"


TERM_MODE = TerminalStyle.MODERN


class ConfigError(Exception):
    """Raised when configuration (.env or settings) is missing or invalid."""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

# ==============================================================================
# INTERNATIONALIZATION (i18n) - NO, SV, FI, EN
# ==============================================================================
class Language:
    NO = "no"
    SV = "sv"
    FI = "fi"
    EN = "en"


DEFAULT_LANGUAGE = Language.NO

TRANSLATIONS: dict[str, dict[str, str]] = {
    "no": {
        "now": "Nå",
        "min": "min",
        "on_time": "I rute",
        "delayed": "min forsinket",
        "early": "min tidlig",
        "no_realtime": "mangler sanntidsdata",
        "offline_warn": "Frakoblet nettverk. Viser sist lagrede data fra kl. {time}",
        "offline_err": "Frakoblet nettverk. Kunne ikke hente data for {name}.",
        "stop_not_found": "Fant ikke stoppested med ID '{id}' hos {provider}.",
        "clock": "Klokke",
        "scheduled": "planlagt",
        "offline_tag": "frakoblet",
        "fetching": "Henter avgangsinfo...",
        "exiting": "Avslutter...",
        "no_departures": "Ingen planlagte avganger i valgt tidsvindu.",
        "no_data": "Ingen data tilgjengelig.",
        "bus": "Buss",
        "tram": "Trikk",
        "rail": "Tog",
        "metro": "T-bane",
        "water": "Båt",
        "ferry": "Ferge",
        "air": "Fly",
        "unknown": "Ukjent",
        "clearsky": "Klarvær",
        "fair": "Lettskyet",
        "partlycloudy": "Delvis skyet",
        "cloudy": "Skyet",
        "rain": "Regn",
        "lightrain": "Lett regn",
        "heavyrain": "Kraftig regn",
        "rainshowers": "Regnbyger",
        "lightrainshowers": "Lette regnbyger",
        "heavyrainshowers": "Kraftige regnbyger",
        "sleet": "Sludd",
        "lightsleet": "Lett sludd",
        "heavysleet": "Kraftig sludd",
        "snow": "Snø",
        "lightsnow": "Lett snø",
        "heavysnow": "Kraftig snø",
        "snowshowers": "Snøbyger",
        "fog": "Tåke",
        "err_no_stops_file": "Feil: Fant ikke stoppesteder-filen på: {path}",
        "create_stops_file": "Du må opprette filen 'stoppesteder.txt' og legge stoppestedene der.",
        "see_example_file": "Se på 'stoppesteder_eksempel.txt' for hvordan filen skal se ut.",
        "find_stops_url": "Du kan finne stoppesteder på https://stoppesteder.entur.org",
        "err_empty_section": "Feil på linje {line} i {path}: Tom seksjon '[]'.",
        "err_no_section_header": "Feil i {path}: Stoppesteder må plasseres under en seksjon (f.eks. [hjem] eller [jobb]).",
        "line_missing_header": "Linje {line}: '{text}' mangler overskrift/seksjon.",
        "err_no_profiles_found": "Feil: Ingen profiler/seksjoner funnet i {path}.",
        "define_at_least_one": "Definer minst én seksjon med stoppesteder, f.eks.:",
        "err_reading_file": "Feil under lesing av {path}: {err}",
        "err_no_env": "Feil: Fant ikke konfigurasjonsfilen: {path}",
        "create_env_file": "Du må opprette en '.env'-fil i prosjektmappen basert på '.env_example'.",
        "err_missing_client_name": "Feil: Mangler gyldig 'ET_CLIENT_NAME' i {path}",
        "client_name_format": "Filen må inneholde en unik identifikator på formen:",
        "err_profile_not_found": "Feil: Profil '{profile}' finnes ikke i stoppesteder.txt.",
        "available_profiles": "Tilgjengelige profiler: {profiles}",
        "err_no_stops_active": "Feil: Ingen stoppesteder funnet for valgt profil.",
    },
    "sv": {
        "now": "Nu",
        "min": "min",
        "on_time": "I tid",
        "delayed": "min försenad",
        "early": "min tidig",
        "no_realtime": "saknar realtidsdata",
        "offline_warn": "Frånkopplad från nätverket. Visar sparade data från kl. {time}",
        "offline_err": "Frånkopplad från nätverket. Kunde inte hämta data för {name}.",
        "stop_not_found": "Hittade inte hållplats med ID '{id}' hos {provider}.",
        "clock": "Klocka",
        "scheduled": "tidtabell",
        "offline_tag": "offline",
        "fetching": "Hämtar avgångar...",
        "exiting": "Avslutar...",
        "no_departures": "Inga planerade avgångar inom vald tidsram.",
        "no_data": "Inga data tillgängliga.",
        "bus": "Buss",
        "tram": "Spårvagn",
        "rail": "Tåg",
        "metro": "Tunnelbana",
        "water": "Båt",
        "ferry": "Färja",
        "air": "Flyg",
        "unknown": "Okänd",
        "clearsky": "Klart",
        "fair": "Lätt molnighet",
        "partlycloudy": "Halvklart",
        "cloudy": "Mulet",
        "rain": "Regn",
        "lightrain": "Lätt regn",
        "heavyrain": "Kraftigt regn",
        "rainshowers": "Regnskurar",
        "lightrainshowers": "Lätta regnskurar",
        "heavyrainshowers": "Kraftiga regnskurar",
        "sleet": "Snöblandat regn",
        "lightsleet": "Lätt snöblandat regn",
        "heavysleet": "Kraftigt snöblandat regn",
        "snow": "Snö",
        "lightsnow": "Lätt snöfall",
        "heavysnow": "Kraftigt snöfall",
        "snowshowers": "Snöbyar",
        "fog": "Dimma",
        "err_no_stops_file": "Fel: Hittade inte hållplatsfilen på: {path}",
        "create_stops_file": "Du måste skapa filen 'stoppesteder.txt' och lägga till hållplatserna där.",
        "see_example_file": "Se 'stoppesteder_eksempel.txt' för hur filen ska se ut.",
        "find_stops_url": "Du kan hitta hållplatser på https://stoppesteder.entur.org",
        "err_empty_section": "Fel på rad {line} i {path}: Tom sektion '[]'.",
        "err_no_section_header": "Fel i {path}: Hållplatser måste placeras under en sektion (t.ex. [hemma] eller [jobb]).",
        "line_missing_header": "Rad {line}: '{text}' saknar sektionsrubrik.",
        "err_no_profiles_found": "Fel: Inga profiler/sektioner hittades i {path}.",
        "define_at_least_one": "Definiera minst en sektion med hållplatser, t.ex.:",
        "err_reading_file": "Fel vid läsning av {path}: {err}",
        "err_no_env": "Fel: Hittade inte konfigurationsfilen: {path}",
        "create_env_file": "Du måste skapa en '.env'-fil i projektmappen baserad på '.env_example'.",
        "err_missing_client_name": "Fel: Saknar giltigt 'ET_CLIENT_NAME' i {path}",
        "client_name_format": "Filen måste innehålla en unik identifierare i formatet:",
        "err_profile_not_found": "Fel: Profilen '{profile}' finns inte i stoppesteder.txt.",
        "available_profiles": "Tillgängliga profiler: {profiles}",
        "err_no_stops_active": "Fel: Inga hållplatser hittades för den valda profilen.",
    },
    "fi": {
        "now": "Nyt",
        "min": "min",
        "on_time": "Aikataulussa",
        "delayed": "min myöhässä",
        "early": "min etuajassa",
        "no_realtime": "ei reaaliaikatietoja",
        "offline_warn": "Verkkoyhteys poikki. Näytetään aiemmat tiedot klo {time}",
        "offline_err": "Verkkoyhteys poikki. Tietoja ei saatu kohteelle {name}.",
        "stop_not_found": "Pysäkkiä ei löytynyt tunnuksella '{id}' palvelusta {provider}.",
        "clock": "Aika",
        "scheduled": "aikataulu",
        "offline_tag": "offline",
        "fetching": "Haetaan lähtöaikoja...",
        "exiting": "Lopetetaan...",
        "no_departures": "Ei lähtöjä valitulla aikavälillä.",
        "no_data": "Ei tietoja saatavilla.",
        "bus": "Bussi",
        "tram": "Spora",
        "rail": "Juna",
        "metro": "Metro",
        "water": "Laiva",
        "ferry": "Lautta",
        "air": "Lento",
        "unknown": "Tuntematon",
        "clearsky": "Selkeää",
        "fair": "Puolipilvistä",
        "partlycloudy": "Puolipilvistä",
        "cloudy": "Pilvistä",
        "rain": "Sadetta",
        "lightrain": "Kevyttä sadetta",
        "heavyrain": "Rankkasadetta",
        "rainshowers": "Sadekuuroja",
        "lightrainshowers": "Heikkoja sadekuuroja",
        "heavyrainshowers": "Voimakkaita sadekuuroja",
        "sleet": "Räntäsadetta",
        "lightsleet": "Heikkoa räntäsadetta",
        "heavysleet": "Voimakasta räntäsadetta",
        "snow": "Lumisadetta",
        "lightsnow": "Heikkoa lumisadetta",
        "heavysnow": "Rankkaa lumisadetta",
        "snowshowers": "Lumikuuroja",
        "fog": "Sumua",
        "err_no_stops_file": "Virhe: Pysäkkitiedostoa ei löytynyt: {path}",
        "create_stops_file": "Luo tiedosto 'stoppesteder.txt' ja lisää pysäkit sinne.",
        "see_example_file": "Katso tiedostosta 'stoppesteder_eksempel.txt' mallia.",
        "find_stops_url": "Voit etsiä pysäkkejä osoitteesta https://stoppesteder.entur.org",
        "err_empty_section": "Virhe rivillä {line} tiedostossa {path}: Tyhjä osio '[]'.",
        "err_no_section_header": "Virhe tiedostossa {path}: Pysäkit on sijoitettava osion alle (esim. [koti] tai [tyo]).",
        "line_missing_header": "Rivi {line}: '{text}' puuttuu osio-otsikko.",
        "err_no_profiles_found": "Virhe: Osioita ei löytynyt tiedostosta {path}.",
        "define_at_least_one": "Määritä vähintään yksi osio ja pysäkki, esim.:",
        "err_reading_file": "Virhe luettaessa tiedostoa {path}: {err}",
        "err_no_env": "Virhe: Asetustiedostoa ei löytynyt: {path}",
        "create_env_file": "Luo '.env'-tiedosto projektikansioon '.env_example'-tiedoston pohjalta.",
        "err_missing_client_name": "Virhe: 'ET_CLIENT_NAME' puuttuu tiedostosta {path}",
        "client_name_format": "Tiedoston on sisällettävä yksilöllinen tunniste muodossa:",
        "err_profile_not_found": "Virhe: Profiilia '{profile}' ei löydy tiedostosta stoppesteder.txt.",
        "available_profiles": "Käytettävissä olevat profiilit: {profiles}",
        "err_no_stops_active": "Virhe: Valitulle profiilille ei löytynyt pysäkkejä.",
    },
    "en": {
        "now": "Now",
        "min": "min",
        "on_time": "On time",
        "delayed": "min delayed",
        "early": "min early",
        "no_realtime": "no realtime data",
        "offline_warn": "Network offline. Showing cached data from {time}",
        "offline_err": "Network offline. Failed to fetch data for {name}.",
        "stop_not_found": "Stop not found with ID '{id}' at {provider}.",
        "clock": "Time",
        "scheduled": "scheduled",
        "offline_tag": "offline",
        "fetching": "Fetching departures...",
        "exiting": "Exiting...",
        "no_departures": "No scheduled departures in selected window.",
        "no_data": "No data available.",
        "bus": "Bus",
        "tram": "Tram",
        "rail": "Train",
        "metro": "Metro",
        "water": "Boat",
        "ferry": "Ferry",
        "air": "Flight",
        "unknown": "Unknown",
        "clearsky": "Clear sky",
        "fair": "Fair",
        "partlycloudy": "Partly cloudy",
        "cloudy": "Cloudy",
        "rain": "Rain",
        "lightrain": "Light rain",
        "heavyrain": "Heavy rain",
        "rainshowers": "Rain showers",
        "lightrainshowers": "Light rain showers",
        "heavyrainshowers": "Heavy rain showers",
        "sleet": "Sleet",
        "lightsleet": "Light sleet",
        "heavysleet": "Heavy sleet",
        "snow": "Snow",
        "lightsnow": "Light snow",
        "heavysnow": "Heavy snow",
        "snowshowers": "Snow showers",
        "fog": "Fog",
        "err_no_stops_file": "Error: Stop places file not found at: {path}",
        "create_stops_file": "Please create 'stoppesteder.txt' and list your stop places there.",
        "see_example_file": "See 'stoppesteder_eksempel.txt' for reference.",
        "find_stops_url": "Find stop places at https://stoppesteder.entur.org",
        "err_empty_section": "Error on line {line} in {path}: Empty section '[]'.",
        "err_no_section_header": "Error in {path}: Stops must be placed under a section header (e.g. [home] or [work]).",
        "line_missing_header": "Line {line}: '{text}' is missing a section header.",
        "err_no_profiles_found": "Error: No sections/profiles found in {path}.",
        "define_at_least_one": "Define at least one section with stop places, e.g.:",
        "err_reading_file": "Error reading {path}: {err}",
        "err_no_env": "Error: Configuration file not found at: {path}",
        "create_env_file": "Please create '.env' in the project directory based on '.env_example'.",
        "err_missing_client_name": "Error: Missing valid 'ET_CLIENT_NAME' in {path}",
        "client_name_format": "The file must contain a unique client identifier formatted as:",
        "err_profile_not_found": "Error: Profile '{profile}' not found in stoppesteder.txt.",
        "available_profiles": "Available profiles: {profiles}",
        "err_no_stops_active": "Error: No stop places found for active profile.",
    },
}

CURRENT_LANG = DEFAULT_LANGUAGE


def t(key: str, **kwargs: Any) -> str:
    """Translates a message key to the active language."""
    text = TRANSLATIONS.get(CURRENT_LANG, TRANSLATIONS["no"]).get(
        key, TRANSLATIONS["en"].get(key, key)
    )
    if kwargs:
        return text.format(**kwargs)
    return text


TRANSPORT_EMOJIS = {
    "bus": "🚌",
    "coach": "🚌",
    "tram": "🚋",
    "rail": "🚆",
    "metro": "🚇",
    "water": "⛴️ ",
    "ferry": "⛴️ ",
    "air": "✈️ ",
}

WEATHER_EMOJIS = {
    "clearsky": "☀️",
    "fair": "🌤️",
    "partlycloudy": "⛅",
    "cloudy": "☁️",
    "rain": "🌧️",
    "lightrain": "🌦️",
    "heavyrain": "🌧️",
    "rainshowers": "🌦️",
    "lightrainshowers": "🌦️",
    "heavyrainshowers": "🌧️",
    "sleet": "🌨️",
    "lightsleet": "🌨️",
    "heavysleet": "🌨️",
    "snow": "❄️",
    "lightsnow": "🌨️",
    "heavysnow": "❄️",
    "snowshowers": "🌨️",
    "fog": "🌫️",
}


@dataclass
class WeatherObservation:
    temperature_c: float
    wind_ms: float
    wind_gust_ms: float | None
    wind_direction_degrees: float
    wind_direction_text: str
    wind_arrow: str
    symbol_code: str
    description: str
    symbol_emoji: str
    fetched_at_iso: str


@dataclass
class DepartureCall:
    line_code: str
    transport_mode: str
    destination: str
    aimed_iso: str
    expected_iso: str
    is_realtime: bool


@dataclass
class NormalizedStopData:
    name: str
    latitude: float | None
    longitude: float | None
    departures: list[DepartureCall]


@dataclass
class StopPlaceState:
    name: str
    raw_id: str
    clean_id: str
    provider: str
    normalized_data: NormalizedStopData | None = None
    error_message: str | None = None
    last_updated: arrow.Arrow | None = None
    weather: WeatherObservation | None = None


# ==============================================================================
# DISK-BASED WEATHER CACHE AND MET API
# ==============================================================================
def degrees_to_wind_direction(degrees: float) -> tuple[str, str]:
    """
    Converts meteorological wind direction (degrees FROM where the wind blows)
    into a 16-point compass label and arrow pointing in flow direction.
    """
    compass_names = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
    ]
    # Localized compass names
    if CURRENT_LANG in ("no", "sv"):
        compass_names = [
            "N", "NNØ", "NØ", "ØNØ", "Ø", "ØSØ", "SØ", "SSØ",
            "S", "SSV", "SV", "VSV", "V", "VNV", "NV", "NNV"
        ]
    elif CURRENT_LANG == "fi":
        compass_names = [
            "P", "PPO", "PO", "I-PO", "I", "I-KA", "KA", "E-KA",
            "E", "E-LO", "LO", "L-LO", "L", "L-LU", "LU", "P-LU"
        ]

    arrows = [
        "↓", "↙", "↙", "↙", "←", "↖", "↖", "↖",
        "↑", "↗", "↗", "↗", "→", "↘", "↘", "↘"
    ]

    index = int((degrees + 11.25) % 360 // 22.5)
    return compass_names[index], arrows[index]


class WeatherCache:
    """Handles reading, writing and caching weather forecasts on disk."""

    def __init__(self, cache_path: Path = WEATHER_CACHE_FILE):
        self.cache_path = cache_path
        self._data: dict[str, dict[str, Any]] = self._load_from_disk()

    def _load_from_disk(self) -> dict[str, dict[str, Any]]:
        if not self.cache_path.is_file():
            return {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.warning("Failed to read weather cache: %s", e)
            return {}

    def _save_to_disk(self) -> None:
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.warning(f"Failed to save weather cache: {e}")  

    @staticmethod
    def _make_key(lat: float, lon: float) -> str:
        return f"{lat:.3f},{lon:.3f}"

    def get_weather(self, lat: float, lon: float) -> WeatherObservation | None:
        key = self._make_key(lat, lon)
        entry = self._data.get(key)
        if not entry:
            return None

        try:
            fetched_time = arrow.get(entry["fetched_at_iso"])
            age_seconds = (arrow.now() - fetched_time).total_seconds()
            if age_seconds > WEATHER_CACHE_DURATION_SECONDS:
                return None
            return WeatherObservation(**entry)
        except Exception:
            return None

    def save_weather(self, lat: float, lon: float, weather: WeatherObservation) -> None:
        key = self._make_key(lat, lon)
        self._data[key] = {
            "temperature_c": weather.temperature_c,
            "wind_ms": weather.wind_ms,
            "wind_gust_ms": weather.wind_gust_ms,
            "wind_direction_degrees": weather.wind_direction_degrees,
            "wind_direction_text": weather.wind_direction_text,
            "wind_arrow": weather.wind_arrow,
            "symbol_code": weather.symbol_code,
            "description": weather.description,
            "symbol_emoji": weather.symbol_emoji,
            "fetched_at_iso": weather.fetched_at_iso,
        }
        self._save_to_disk()


weather_cache = WeatherCache()


def parse_weather_symbol(raw_code: str) -> tuple[str, str]:
    """Extracts emoji and localized description from MET symbol_code."""
    base_code = raw_code.split("_")[0]
    emoji = WEATHER_EMOJIS.get(base_code, "🌡️")
    desc = t(base_code) if base_code in TRANSLATIONS.get(CURRENT_LANG, {}) else raw_code.capitalize()
    return emoji, desc


def fetch_weather_from_met(
    session: requests.Session, lat: float, lon: float
) -> WeatherObservation | None:
    """Fetches current weather observation from MET Norway with caching."""
    cached = weather_cache.get_weather(lat, lon)
    if cached is not None:
        return cached

    user_agent = config.get("MET_USER_AGENT")
    if not user_agent or not str(user_agent).strip():
        raise ConfigError(
            "Missing required config 'MET_USER_AGENT' in .env.\n"
            "Meteorologisk institutt (MET Norway) requires that all clients identify themselves\n"
            "with an application name and contact info (e.g. email or URL).\n"
            "Example in .env: MET_USER_AGENT=\"MyTransitApp/1.0 (contact: user@example.com)\""
        )

    headers = {
        "User-Agent": str(user_agent).strip(),
        "Accept": "application/json",
    }
    params = {"lat": f"{lat:.4f}", "lon": f"{lon:.4f}"}

    try:
        res = session.get(
            MET_LOCATIONFORECAST_URL,
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if res.status_code != 200:
            logging.warning("MET API returned HTTP %s for lat=%s lon=%s", res.status_code, lat, lon)
            return None

        body = res.json()
        now_timeseries = body["properties"]["timeseries"][0]["data"]
        instant = now_timeseries["instant"]["details"]
        temp = instant.get("air_temperature", 0.0)
        wind = instant.get("wind_speed", 0.0)
        wind_gust_raw = instant.get("wind_speed_of_gust")
        wind_gust = float(wind_gust_raw) if wind_gust_raw is not None else None
        wind_dir = float(instant.get("wind_from_direction", 0.0))

        wind_text, wind_arrow = degrees_to_wind_direction(wind_dir)

        next_1h = now_timeseries.get("next_1_hours") or now_timeseries.get("next_6_hours") or {}
        summary = next_1h.get("summary", {})
        raw_symbol = summary.get("symbol_code", "clearsky")

        emoji, description = parse_weather_symbol(raw_symbol)

        observation = WeatherObservation(
            temperature_c=float(temp),
            wind_ms=float(wind),
            wind_gust_ms=wind_gust,
            wind_direction_degrees=wind_dir,
            wind_direction_text=wind_text,
            wind_arrow=wind_arrow,
            symbol_code=raw_symbol,
            description=description,
            symbol_emoji=emoji,
            fetched_at_iso=arrow.now().isoformat(),
        )

        weather_cache.save_weather(lat, lon, observation)
        return observation
    except Exception as e:
        logging.warning("Error fetching weather: %s", e)
        return None


# ==============================================================================
# CONFIG FILE PARSING
# ==============================================================================
def load_stop_places(file_path: Path | None = None) -> dict[str, dict[str, str]]:
    """
    Reads stop places grouped by sections ([home], [work], etc.) from file.
    Returns: {'home': {'Stop1': 'ID1', ...}, 'work': {...}}
    """
    if file_path is None:
        file_path = BASE_DIR / "stoppesteder.txt"

    if not file_path.is_file():
        print(t("err_no_stops_file", path=file_path))
        print(t("create_stops_file"))
        print(t("see_example_file"))
        print(t("find_stops_url"))
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
                        print(t("err_empty_section", line=line_no, path=file_path))
                        sys.exit(1)
                    if active_profile not in profiles:
                        profiles[active_profile] = {}
                    continue

                if "=" not in line:
                    continue

                if active_profile is None:
                    print(t("err_no_section_header", path=file_path))
                    print(t("line_missing_header", line=line_no, text=line))
                    sys.exit(1)

                name, nsr_id = line.split("=", 1)
                clean_name = name.strip().strip('"').strip("'")
                clean_id = nsr_id.strip().strip('"').strip("'")

                profiles[active_profile][clean_name] = clean_id

        if not profiles:
            print(t("err_no_profiles_found", path=file_path))
            print(t("define_at_least_one"))
            print('[home]\nKlimavegen = "NSR:StopPlace:53434"')
            sys.exit(1)

        return profiles
    except OSError as e:
        logging.error("Failed to read stop places file: %s", e)
        print(t("err_reading_file", path=file_path, err=e))
        sys.exit(1)


# ==============================================================================
# FORMATTING HELPERS
# ==============================================================================
def minutes_until_departure(expected_iso_str: str) -> str:
    """Calculates remaining minutes until departure based on expected time."""
    expected_time = arrow.get(expected_iso_str)
    now = arrow.now(expected_time.tzinfo)
    diff_seconds = (expected_time - now).total_seconds()
    minutes_left = int(diff_seconds // 60)

    if minutes_left <= 0:
        return t("now")
    elif minutes_left == 1:
        return f"1 {t('min')}"
    else:
        return f"{minutes_left} {t('min')}"


def format_transport_mode(transport_mode: str | None) -> str:
    """Formats transport mode with emoji and localized text."""
    mode_key = (transport_mode or "").lower()
    localized_name = t(mode_key) if mode_key in TRANSLATIONS.get(CURRENT_LANG, {}) else (mode_key.capitalize() or t("unknown"))

    match TERM_MODE:
        case TerminalStyle.MODERN:
            emoji = TRANSPORT_EMOJIS.get(mode_key, "🚏")
            return f"{emoji} {localized_name:<7}"
        case _:
            return f"{localized_name:<7}"


def format_delay_modern(delay_minutes: int) -> str:
    if delay_minutes > 0:
        return f"🔴 {delay_minutes} {t('delayed')}"
    elif delay_minutes < 0:
        return f"💚 {abs(delay_minutes)} {t('early')}"
    else:
        return f"💚 {t('on_time')}"


def format_delay_classic(delay_minutes: int) -> str:
    red = "\033[91m"
    green = "\033[92m"
    reset = "\033[0m"

    if delay_minutes > 0:
        return f"{red}[!] {delay_minutes} {t('delayed')}{reset}"
    elif delay_minutes < 0:
        return f"{green}[+] {abs(delay_minutes)} {t('early')}{reset}"
    else:
        return f"{green}[V] {t('on_time')}{reset}"


def format_delay(aimed_raw: str, expected_raw: str) -> str:
    aimed = arrow.get(aimed_raw)
    expected = arrow.get(expected_raw)
    diff_seconds = (expected - aimed).total_seconds()
    delay_minutes = int(diff_seconds // 60)

    match TERM_MODE:
        case TerminalStyle.MODERN:
            return format_delay_modern(delay_minutes)
        case _:
            return format_delay_classic(delay_minutes)


def iso_to_time_str(time_str: str, format_str: str = "HH:mm") -> str:
    return arrow.get(time_str).format(format_str)


def clear_terminal() -> None:
    command = "cls" if sys.platform.startswith("win") else "clear"
    try:
        subprocess.run([command], check=True)
    except Exception:
        pass


def make_terminal_hyperlink(url: str, text: str) -> str:
    """Wraps text in OSC 8 ANSI escape sequence for clickable terminal hyperlinks."""
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def format_weather_header(weather: WeatherObservation | None) -> str:
    """Formats localized weather information for stop header."""
    if not weather:
        return ""

    if weather.wind_gust_ms and weather.wind_gust_ms > weather.wind_ms:
        wind_str = f"{weather.wind_ms:.1f} ({weather.wind_gust_ms:.1f}) m/s"
    else:
        wind_str = f"{weather.wind_ms:.1f} m/s"

    degrees_int = int(round(weather.wind_direction_degrees))

    if TERM_MODE == TerminalStyle.MODERN:
        return (
            f" ({weather.symbol_emoji} {weather.temperature_c:.0f}°C, {weather.description}, "
            f"💨 {wind_str} {weather.wind_arrow} {weather.wind_direction_text} {degrees_int}°)"
        )
    else:
        return (
            f" ({weather.temperature_c:.0f}C, {weather.description}, "
            f"{wind_str} {weather.wind_direction_text} {degrees_int}deg)"
        )


# ==============================================================================
# PROVIDER ROUTING & API CLIENTS (ADAPTERS)
# ==============================================================================
def detect_provider(raw_id: str) -> tuple[str, str]:
    """
    Determines provider ('entur', 'digitransit_hsl', 'digitransit_finland', etc.)
    and returns (provider, clean_id).

    Supports explicit country prefixes:
      - 'NO:...' -> Entur
      - 'FI:...' -> Digitransit HSL
      - 'FINLAND:...' -> Digitransit Finland national
      - 'SE:...' -> ResRobot (Sweden)
      - 'DK:...' -> Rejseplanen (Denmark)

    Or direct native feed IDs:
      - 'NSR:...' -> Entur (Norway)
      - 'HSL:...' or 'HKI:...' -> Digitransit HSL (Helsinki)
      - 'tampere:...', 'waltti:...' -> Digitransit Finland national
    """
    cleaned = raw_id.strip()
    id_lower = cleaned.lower()

    # 1. Explicit 2-letter / country prefixes: NO:, FI:, SE:, DK:, FINLAND:
    country_map = {
        "no": "entur",
        "fi": "digitransit_hsl",
        "finland": "digitransit_finland",
        "se": "resrobot",
        "dk": "rejseplanen",
    }

    if ":" in cleaned:
        first_part, rest = cleaned.split(":", 1)
        first_lower = first_part.strip().lower()
        if first_lower in country_map:
            return country_map[first_lower], rest.strip()

    # 2. Native feed / agency prefix checks
    if id_lower.startswith("nsr:"):
        return "entur", cleaned
    if id_lower.startswith(("hsl:", "hki:")):
        return "digitransit_hsl", cleaned
    if id_lower.startswith(("tampere:", "waltti:", "matka:", "vr:")):
        return "digitransit_finland", cleaned

    # 3. Numeric patterns for Sweden (74xxxxxxx) and Denmark (86xxxxxxx / 0086xxxxxxx)
    if id_lower.startswith("74") and len(id_lower) == 9 and id_lower.isdigit():
        return "resrobot", cleaned
    if (id_lower.startswith("0086") or id_lower.startswith("86")) and id_lower.isdigit():
        return "rejseplanen", cleaned

    # 4. Default fallback to Entur
    return "entur", cleaned


# --- Entur (Norway) Adapter ---
def fetch_entur_stop(
    session: requests.Session,
    clean_id: str,
    time_range_seconds: int,
    departures_count: int,
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
    client_name = config.get("ET_CLIENT_NAME")
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

    departures: list[DepartureCall] = []
    for call in stop_place.get("estimatedCalls") or []:
        line_info = call.get("serviceJourney", {}).get("journeyPattern", {}).get("line", {})
        line_code = line_info.get("publicCode") or "?"
        mode = line_info.get("transportMode") or "bus"
        dest = call.get("destinationDisplay", {}).get("frontText") or t("unknown")

        aimed = call.get("aimedDepartureTime") or call.get("aimedArrivalTime")
        expected = call.get("expectedDepartureTime") or call.get("expectedArrivalTime")
        if not aimed or not expected:
            continue

        departures.append(
            DepartureCall(
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


# --- Digitransit (Finland) Adapter ---
def fetch_digitransit_stop(
    session: requests.Session,
    clean_id: str,
    time_range_seconds: int,
    departures_count: int,
    api_url: str = DIGITRANSIT_HSL_URL,
) -> NormalizedStopData:
    raw_id = clean_id.strip()
    # Generer kandidater for ID: både med og uten HSL: prefiks
    bare_id = raw_id[4:].strip() if raw_id.upper().startswith("HSL:") else raw_id
    id_with_prefix = f"HSL:{bare_id}"

    # Vi tester både id_with_prefix og bare_id i samme GraphQL-forespørsel med aliaser
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
    sub_key = config.get("DIGITRANSIT_SUBSCRIPTION_KEY") or config.get("digitransitSubscriptionKey")
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
        raise requests.HTTPError(f"Digitransit HTTP {res.status_code}: {res.text[:100]}")

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
        raise LookupError(f"Stop not found in Digitransit (tested '{id_with_prefix}' and '{bare_id}')")

    departures: list[DepartureCall] = []
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
        dest = st.get("headsign") or t("unknown")

        service_day = st.get("serviceDay", int(time.time()))
        sched_sec = st.get("scheduledDeparture", 0)
        real_sec = st.get("realtimeDeparture", sched_sec)

        aimed_iso = arrow.get(service_day + sched_sec).isoformat()
        expected_iso = arrow.get(service_day + real_sec).isoformat()

        departures.append(
            DepartureCall(
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

    lat = stop_data.get("lat")
    lon = stop_data.get("lon")
    return NormalizedStopData(
        name=stop_data.get("name") or clean_id,
        latitude=float(lat) if lat is not None else None,
        longitude=float(lon) if lon is not None else None,
        departures=departures,
    )


def fetch_and_update_departures(
    session: requests.Session,
    stops_state: dict[str, StopPlaceState],
    time_range_seconds: int,
    departures_count: int,
) -> None:
    """Fetches departure updates using appropriate country/API adapter, then updates weather."""
    for alias_name, state in stops_state.items():
        try:
            if state.provider == "entur":
                norm = fetch_entur_stop(session, state.clean_id, time_range_seconds, departures_count)
            elif state.provider == "digitransit_hsl":
                norm = fetch_digitransit_stop(session, state.clean_id, time_range_seconds, departures_count, DIGITRANSIT_HSL_URL)
            elif state.provider == "digitransit_finland":
                norm = fetch_digitransit_stop(session, state.clean_id, time_range_seconds, departures_count, DIGITRANSIT_FINLAND_URL)
            elif state.provider == "resrobot":
                raise NotImplementedError("ResRobot (Sweden) adapter requires API key configuration.")
            elif state.provider == "rejseplanen":
                raise NotImplementedError("Rejseplanen (Denmark) adapter requires API key configuration.")
            else:
                norm = fetch_entur_stop(session, state.clean_id, time_range_seconds, departures_count)

            state.normalized_data = norm
            state.error_message = None
            state.last_updated = arrow.now()

            if norm.latitude is not None and norm.longitude is not None:
                state.weather = fetch_weather_from_met(session, norm.latitude, norm.longitude)

        except ConfigError as ce:
            # Fatal configuration error: crash program immediately with clear message
            print(f"\nConfiguration Error: {ce}")
            sys.exit(1)
        except LookupError as le:
            state.error_message = f"NOT_FOUND:{le}"
            logging.warning("Stop lookup error for %s (%s, %s): %s", alias_name, state.clean_id, state.provider, le)
        except requests.RequestException as re:
            state.error_message = f"NETWORK:{re}"
            logging.warning("Network error for %s (%s, %s): %s", alias_name, state.clean_id, state.provider, re)
        except (ValueError, Exception) as e:
            state.error_message = f"API_ERROR:{e}"
            logging.warning("API error for %s (%s, %s): %s", alias_name, state.clean_id, state.provider, e)


# ==============================================================================
# RENDERING
# ==============================================================================
def render_stop_place(alias_name: str, state: StopPlaceState, terminal_width: int) -> None:
    """Renders upcoming departures and weather for a single stop in terminal."""
    has_fresh_data = state.error_message is None and state.normalized_data is not None
    norm = state.normalized_data

    display_name = norm.name if norm and norm.name else alias_name
    weather_text = format_weather_header(state.weather)

    yr_url: str | None = None
    if norm and norm.latitude is not None and norm.longitude is not None:
        yr_url = f"https://www.yr.no/nb/værvarsel/daglig-tabell/{norm.latitude:.4f},{norm.longitude:.4f}"

    if yr_url and TERM_MODE == TerminalStyle.MODERN:
        linked_name = make_terminal_hyperlink(yr_url, display_name)
        linked_pin = make_terminal_hyperlink(yr_url, "📍")
        visible_length = len(f" {display_name}{weather_text} ")
        side_dashes = max(1, (terminal_width - visible_length) // 2)
        left = "-" * side_dashes
        right = "-" * (terminal_width - visible_length - side_dashes)
        print(f"{left} {linked_name}{weather_text} {right}{linked_pin}")
    else:
        header_text = f" {display_name}{weather_text} "
        print(f"{header_text:-^{terminal_width}}📍")

    if state.error_message:
        yellow = "\033[93m" if TERM_MODE != TerminalStyle.CLASSIC else ""
        reset = "\033[0m" if TERM_MODE != TerminalStyle.CLASSIC else ""

        if state.error_message.startswith("NOT_FOUND:"):
            icon = "❓" if TERM_MODE != TerminalStyle.CLASSIC else "[?]"
            err_msg = t("stop_not_found", id=state.clean_id, provider=state.provider)
            print(f" {yellow}{icon} {err_msg}{reset}")
            return
        elif state.error_message.startswith("API_ERROR:"):
            icon = "⚠️" if TERM_MODE != TerminalStyle.CLASSIC else "[!]"
            detalj = state.error_message.split(":", 1)[1]
            print(f" {yellow}{icon} API feil ({state.provider}): {detalj[:80]}{reset}")
            return
        elif state.normalized_data and state.last_updated:
            last_time = state.last_updated.format("HH:mm:ss")
            icon = "📡" if TERM_MODE != TerminalStyle.CLASSIC else "[!]"
            warn_msg = t("offline_warn", time=last_time)
            print(f" {yellow}{icon} {warn_msg}{reset}")
        else:
            icon = "📡" if TERM_MODE != TerminalStyle.CLASSIC else "[X]"
            err_msg = t("offline_err", name=display_name)
            print(f" {icon} {err_msg}")
            return

    if not norm:
        print(f"  {t('no_data')}")
        return

    departures = norm.departures
    if not departures:
        print(f"  {t('no_departures')}")
        return

    for call in departures:
        mode_str = format_transport_mode(call.transport_mode)
        line_code = call.line_code
        destination = call.destination

        aimed_clock = iso_to_time_str(call.aimed_iso)
        expected_clock = iso_to_time_str(call.expected_iso)

        if has_fresh_data:
            time_left = minutes_until_departure(call.expected_iso)
            delay = format_delay(call.aimed_iso, call.expected_iso)

            if call.is_realtime:
                print(
                    f"{mode_str} {line_code:<5} {destination:33}  "
                    f"{time_left:6}  {expected_clock} ({aimed_clock}) -- {delay:18}"
                )
            else:
                scheduled_time_left = minutes_until_departure(call.aimed_iso)
                print(
                    f"{mode_str} {line_code:<5} {destination:33}  "
                    f"{scheduled_time_left:6}  {aimed_clock} -- {t('no_realtime')}"
                )
        else:
            clock_lbl = t("clock")
            sched_lbl = t("scheduled")
            off_tag = t("offline_tag")
            print(
                f"{mode_str} {line_code:<5} {destination:33}  "
                f"{clock_lbl}: {expected_clock} ({sched_lbl}: {aimed_clock}) [{off_tag}]"
            )


# ==============================================================================
# CLI ARGUMENTS AND MAIN ENTRY POINT
# ==============================================================================
def parse_arguments(all_profiles: dict[str, dict[str, str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Nordic transit departure board with live weather forecast.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

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
    global config, CURRENT_LANG

    # 1. Check for language override early in CLI or .env so errors appear in user's language
    env_path = BASE_DIR / ".env"
    prelim_config = dotenv_values(env_path) if env_path.is_file() else {}
    for i, arg in enumerate(sys.argv):
        if arg == "--lang" and i + 1 < len(sys.argv):
            if sys.argv[i + 1] in TRANSLATIONS:
                CURRENT_LANG = sys.argv[i + 1]
        elif arg.startswith("--lang="):
            val = arg.split("=", 1)[1]
            if val in TRANSLATIONS:
                CURRENT_LANG = val
    if CURRENT_LANG == DEFAULT_LANGUAGE and prelim_config.get("LANGUAGE") in TRANSLATIONS:
        CURRENT_LANG = prelim_config["LANGUAGE"]

    # 2. Load .env configuration
    if not env_path.is_file():
        print(t("err_no_env", path=env_path))
        print(t("create_env_file"))
        print("Example:")
        print("  cp .env_example .env")
        sys.exit(1)

    config = dotenv_values(env_path)

    # 3. Load stop places and parse CLI arguments
    all_profiles = load_stop_places()
    args = parse_arguments(all_profiles)

    # Apply parsed language argument if explicitly specified
    if args.lang and args.lang in TRANSLATIONS:
        CURRENT_LANG = args.lang

    # 4. Select active profile
    chosen_profile = args.profile or (args.positional_profile.lower() if args.positional_profile else None)

    if chosen_profile:
        if chosen_profile not in all_profiles:
            available = ", ".join(f"'{p}'" for p in all_profiles)
            print(t("err_profile_not_found", profile=chosen_profile))
            print(t("available_profiles", profiles=available))
            sys.exit(1)
        active_stops = all_profiles[chosen_profile]
    else:
        first_profile = next(iter(all_profiles.keys()))
        active_stops = all_profiles[first_profile]

    if not active_stops:
        print(t("err_no_stops_active"))
        sys.exit(1)

    # 5. Prepare state per stop place with detected provider
    stops_state: dict[str, StopPlaceState] = {}
    for name, raw_id in active_stops.items():
        prov, clean_id = detect_provider(raw_id)
        stops_state[name] = StopPlaceState(
            name=name,
            raw_id=raw_id,
            clean_id=clean_id,
            provider=prov,
        )

    session = requests.Session()
    clear_terminal()

    # 6. Main execution loop
    try:
        while True:
            print(t("fetching"))
            fetch_and_update_departures(
                session=session,
                stops_state=stops_state,
                time_range_seconds=args.timerange,
                departures_count=args.antall,
            )

            clear_terminal()

            for state in stops_state.values():
                render_stop_place(state.name, state, DEFAULT_TERMINAL_WIDTH)

            print("=" * (DEFAULT_TERMINAL_WIDTH + 1))
            time.sleep(args.intervall)
    except KeyboardInterrupt:
        print(f"\n{t('exiting')}")
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
