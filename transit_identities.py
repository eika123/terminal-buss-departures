from enum import StrEnum

from pydantic import BaseModel, Field

from i18n import Language, translate_international_message


class TransitNamingStyle(StrEnum):
    CULTURAL = "cultural"
    ORIGINAL = "original"
    GENERIC = "generic"


class TransitSystemIdentity(BaseModel):
    system_id: str
    city: str
    country: str
    local_names: dict[str, str] = Field(default_factory=dict)
    signage_codes: dict[str, str] = Field(default_factory=dict)
    exonyms: dict[str, dict[Language, str]] = Field(default_factory=dict)


TRANSIT_SYSTEM_REGISTRY: dict[str, TransitSystemIdentity] = {
    "oslo_ruter": TransitSystemIdentity(
        system_id="oslo_ruter",
        city="Oslo",
        country="NO",
        local_names={"metro": "T-bane", "tram": "Trikk"},
        signage_codes={"metro": "T"},
        exonyms={
            "metro": {
                Language.NO: "T-bane",
                Language.SV: "T-bana",
                Language.FI: "Metro",
                Language.EN: "T-bane",
            },
            "tram": {
                Language.NO: "Trikk",
                Language.SV: "Spårvagn",
                Language.FI: "Ratikka",
                Language.EN: "Tram",
            },
        },
    ),
    "bergen_skyss": TransitSystemIdentity(
        system_id="bergen_skyss",
        city="Bergen",
        country="NO",
        local_names={"tram": "Bybanen"},
        exonyms={
            "tram": {
                Language.NO: "Bybanen",
                Language.SV: "Bybanan",
                Language.FI: "Pikaspora",
                Language.EN: "Light rail",
            },
        },
    ),
    "trondheim_atb": TransitSystemIdentity(
        system_id="trondheim_atb",
        city="Trondheim",
        country="NO",
        local_names={"tram": "Gråkallbanen"},
        exonyms={
            "tram": {
                Language.NO: "Gråkallbanen",
                Language.SV: "Spårvagn",
                Language.FI: "Ratikka",
                Language.EN: "Tram",
            },
        },
    ),
    "helsinki_hsl": TransitSystemIdentity(
        system_id="helsinki_hsl",
        city="Helsinki",
        country="FI",
        local_names={"metro": "Metro", "tram": "Spora"},
        signage_codes={"metro": "M"},
        exonyms={
            "metro": {
                Language.FI: "Metro",
                Language.SV: "Metro",
                Language.NO: "Metro",
                Language.EN: "Metro",
            },
            "tram": {
                Language.FI: "Spora",
                Language.SV: "Spårvagn",
                Language.NO: "Trikk",
                Language.EN: "Tram",
            },
        },
    ),
    "tampere_ratikka": TransitSystemIdentity(
        system_id="tampere_ratikka",
        city="Tampere",
        country="FI",
        local_names={"tram": "Ratikka"},
        exonyms={
            "tram": {
                Language.FI: "Ratikka",
                Language.SV: "Spårvagn",
                Language.NO: "Trikk",
                Language.EN: "Tram",
            },
        },
    ),
    "stockholm_sl": TransitSystemIdentity(
        system_id="stockholm_sl",
        city="Stockholm",
        country="SE",
        local_names={"metro": "T-bana", "tram": "Spårvagn"},
        signage_codes={"metro": "T"},
        exonyms={
            "metro": {
                Language.SV: "T-bana",
                Language.NO: "T-bana",
                Language.FI: "Metro",
                Language.EN: "Metro",
            },
            "tram": {
                Language.SV: "Spårvagn",
                Language.NO: "Trikk",
                Language.FI: "Ratikka",
                Language.EN: "Tram",
            },
        },
    ),
    "london_tfl": TransitSystemIdentity(
        system_id="london_tfl",
        city="London",
        country="GB",
        local_names={"metro": "Tube"},
        signage_codes={"metro": "Underground"},
        exonyms={
            "metro": {
                Language.EN: "Tube",
                Language.NO: "Tuben",
                Language.SV: "Tuben",
                Language.FI: "Metro",
            },
        },
    ),
    "berlin_bvg": TransitSystemIdentity(
        system_id="berlin_bvg",
        city="Berlin",
        country="DE",
        local_names={"metro": "U-Bahn"},
        signage_codes={"metro": "U"},
        exonyms={
            "metro": {
                Language.EN: "U-Bahn",
                Language.NO: "U-Bahn",
                Language.SV: "U-Bahn",
                Language.FI: "Metro",
            },
        },
    ),
}


TRANSIT_PREFIX_SYSTEMS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("hsl:", "hki:"), "helsinki_hsl"),
    (("tampere:",), "tampere_ratikka"),
    (("sl:",), "stockholm_sl"),
    (("tfl:",), "london_tfl"),
)

TRANSIT_GEOFENCE_SYSTEMS: tuple[tuple[str, float, float, float, float], ...] = (
    # system_id, min_lat, max_lat, min_lon, max_lon
    ("oslo_ruter", 59.7, 60.2, 10.3, 11.2),
    ("bergen_skyss", 60.2, 60.6, 5.1, 5.6),
    ("trondheim_atb", 63.3, 63.6, 10.1, 10.6),
    ("helsinki_hsl", 59.9, 60.5, 24.4, 25.3),
    ("tampere_ratikka", 61.3, 61.7, 23.5, 24.1),
    ("stockholm_sl", 59.1, 59.6, 17.7, 18.4),
    ("london_tfl", 51.3, 51.7, -0.5, 0.3),
    ("berlin_bvg", 52.3, 52.7, 13.1, 13.8),
)


def detect_transit_system(
    clean_id: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> str | None:
    """
    Detects the rapid transit system / city network from stop place ID prefix
    or geographic coordinates (geofence).
    """
    if clean_id:
        clean_lower = clean_id.lower().strip()
        for prefixes, sys_id in TRANSIT_PREFIX_SYSTEMS:
            if clean_lower.startswith(prefixes):
                return sys_id

    if latitude is not None and longitude is not None:
        for sys_id, min_lat, max_lat, min_lon, max_lon in TRANSIT_GEOFENCE_SYSTEMS:
            if min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon:
                return sys_id

    return None


def _resolve_cultural_term(system: TransitSystemIdentity, mode_key: str, user_lang: str) -> str | None:
    """Resolves mode name based on cultural exonym or local name."""
    try:
        lang_enum = Language(user_lang)
    except ValueError:
        lang_enum = Language.EN

    if mode_key in system.exonyms and lang_enum in system.exonyms[mode_key]:
        return system.exonyms[mode_key][lang_enum]
    return system.local_names.get(mode_key)


def _resolve_system_term(
    system_id: str,
    mode_key: str,
    user_lang: str,
    naming_style: str,
) -> str | None:
    """Looks up transit mode term from transit system registry."""
    system = TRANSIT_SYSTEM_REGISTRY.get(system_id)
    if not system:
        return None

    if naming_style == TransitNamingStyle.ORIGINAL:
        return system.local_names.get(mode_key)
    if naming_style == TransitNamingStyle.CULTURAL:
        return _resolve_cultural_term(system, mode_key, user_lang)
    return None


def resolve_transit_term(
    mode: str,
    system_id: str | None,
    user_lang: str,
    naming_style: str = TransitNamingStyle.CULTURAL,
    mode_overrides: dict[str, str] | None = None,
    system_overrides: dict[str, str] | None = None,
) -> str:
    """
    Resolves the display name for a transport mode based on transit system,
    user language, naming style, and configuration overrides.
    """
    mode_key = (mode or "").lower()

    # 1. System-specific override (e.g. "oslo_ruter.metro" = "T")
    if system_id and system_overrides:
        specific_key = f"{system_id}.{mode_key}"
        if specific_key in system_overrides:
            return system_overrides[specific_key]

    # 2. Global mode override (e.g. "metro" = "T")
    if mode_overrides and mode_key in mode_overrides:
        return mode_overrides[mode_key]

    # 3. System identity lookup
    if system_id and (term := _resolve_system_term(system_id, mode_key, user_lang, naming_style)):
        return term

    # 4. Standard dictionary fallback
    fallback = translate_international_message(mode_key, lang=user_lang)
    if fallback == mode_key:
        return mode_key.capitalize() or translate_international_message("unknown", lang=user_lang)
    return fallback
