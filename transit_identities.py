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
        if clean_lower.startswith(("hsl:", "hki:")):
            return "helsinki_hsl"
        if clean_lower.startswith("tampere:"):
            return "tampere_ratikka"
        if clean_lower.startswith("sl:"):
            return "stockholm_sl"
        if clean_lower.startswith("tfl:"):
            return "london_tfl"

    if latitude is not None and longitude is not None:
        # Oslo metropolitan area
        if 59.7 <= latitude <= 60.2 and 10.3 <= longitude <= 11.2:
            return "oslo_ruter"
        # Bergen metropolitan area (Bybanen)
        if 60.2 <= latitude <= 60.6 and 5.1 <= longitude <= 5.6:
            return "bergen_skyss"
        # Trondheim area (Gråkallbanen)
        if 63.3 <= latitude <= 63.6 and 10.1 <= longitude <= 10.6:
            return "trondheim_atb"
        # Helsinki metropolitan area
        if 59.9 <= latitude <= 60.5 and 24.4 <= longitude <= 25.3:
            return "helsinki_hsl"
        # Tampere area (Tampereen ratikka)
        if 61.3 <= latitude <= 61.7 and 23.5 <= longitude <= 24.1:
            return "tampere_ratikka"
        # Stockholm area
        if 59.1 <= latitude <= 59.6 and 17.7 <= longitude <= 18.4:
            return "stockholm_sl"
        # London area
        if 51.3 <= latitude <= 51.7 and -0.5 <= longitude <= 0.3:
            return "london_tfl"
        # Berlin area
        if 52.3 <= latitude <= 52.7 and 13.1 <= longitude <= 13.8:
            return "berlin_bvg"

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
    if system_id and system_id in TRANSIT_SYSTEM_REGISTRY:
        system = TRANSIT_SYSTEM_REGISTRY[system_id]
        if naming_style == TransitNamingStyle.ORIGINAL:
            if mode_key in system.local_names:
                return system.local_names[mode_key]
        elif naming_style == TransitNamingStyle.CULTURAL:
            try:
                lang_enum = Language(user_lang)
            except ValueError:
                lang_enum = Language.EN

            if mode_key in system.exonyms and lang_enum in system.exonyms[mode_key]:
                return system.exonyms[mode_key][lang_enum]
            if mode_key in system.local_names:
                return system.local_names[mode_key]

    # 4. Standard dictionary fallback
    fallback = translate_international_message(mode_key, lang=user_lang)
    if fallback == mode_key:
        return mode_key.capitalize() or translate_international_message("unknown", lang=user_lang)
    return fallback
