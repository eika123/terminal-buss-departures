import argparse
from dataclasses import dataclass
import json
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
# KONFIGURASJON OG KONSTANTER
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent
ENTUR_GRAPHQL_URL = "https://api.entur.io/journey-planner/v3/graphql"
MET_LOCATIONFORECAST_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
WEATHER_CACHE_FILE = BASE_DIR / ".weather_cache.json"

DEFAULT_TIME_RANGE_SECONDS = 5400  # 90 minutter (1.5 time)
DEFAULT_DEPARTURES_COUNT = 10
DEFAULT_REFRESH_INTERVAL_SECONDS = 60
DEFAULT_TERMINAL_WIDTH = 95
REQUEST_TIMEOUT_SECONDS = 10
WEATHER_CACHE_DURATION_SECONDS = 1800  # 30 minutter cache for værdata

config: dict[str, Any] = {}


class TermStil:
    MODERNE = "moderne"
    FANCY = "fancy"
    KLASSISK = "klassisk"


TERM_MODE = TermStil.MODERNE

TRANSPORT_MODERNE = {
    "bus": ("🚌", "Buss"),
    "coach": ("🚌", "Buss"),
    "tram": ("🚋", "Trikk"),
    "rail": ("🚆", "Tog"),
    "metro": ("🚇", "T-bane"),
    "water": ("⛴️ ", "Båt"),
    "ferry": ("⛴️ ", "Ferge"),
    "air": ("✈️ ", "Fly"),
}

TRANSPORT_KLASSISK = {
    "bus": "Buss",
    "coach": "Buss",
    "tram": "Trikk",
    "rail": "Tog",
    "metro": "T-bane",
    "water": "Båt",
    "ferry": "Ferge",
    "air": "Fly",
}

# Mapping fra MET symbol_code til emoji og norsk beskrivelse
VAER_SYMBOLER = {
    "clearsky": ("☀️", "Klarvær"),
    "fair": ("🌤️", "Lettskyet"),
    "partlycloudy": ("⛅", "Delvis skyet"),
    "cloudy": ("☁️", "Skyet"),
    "rain": ("🌧️", "Regn"),
    "lightrain": ("🌦️", "Lett regn"),
    "heavyrain": ("🌧️", "Kraftig regn"),
    "rainshowers": ("🌦️", "Regnbyger"),
    "lightrainshowers": ("🌦️", "Lette regnbyger"),
    "heavyrainshowers": ("🌧️", "Kraftige regnbyger"),
    "sleet": ("🌨️", "Sludd"),
    "lightsleet": ("🌨️", "Lett sludd"),
    "heavysleet": ("🌨️", "Kraftig sludd"),
    "snow": ("❄️", "Snø"),
    "lightsnow": ("🌨️", "Lett snø"),
    "heavysnow": ("❄️", "Kraftig snø"),
    "snowshowers": ("🌨️", "Snøbyger"),
    "fog": ("🌫️", "Tåke"),
}


@dataclass
class VaerObservasjon:
    temperatur_c: float
    vind_ms: float
    vindkast_ms: float | None
    vindretning_grader: float
    vindretning_tekst: str
    vind_pil: str
    symbol_kode: str
    beskrivelse: str
    symbol_emoji: str
    hentet_tid_iso: str


@dataclass
class StoppestedData:
    navn: str
    nsr_id: str
    response: dict[str, Any] | None = None
    feilmelding: str | None = None
    sist_oppdatert: arrow.Arrow | None = None
    latitude: float | None = None
    longitude: float | None = None
    vaer: VaerObservasjon | None = None


# ==============================================================================
# DISK-BASERT VÆR-CACHE OG MET-API
# ==============================================================================
def grader_til_vindretning(grader: float) -> tuple[str, str]:
    """
    Gjør om vindretning i grader (hvor vinden BLÅSER FRA) til kompassretning og pil.
    Pilene peker i vindens blåseretning (dit vinden blåser):
    - Nordavind (blåser fra nord sørover): Sørvendt pil ↓
    - Sønnavind (blåser fra sør nordover): Nordvendt pil ↑
    """
    retninger = [
        ("N", "↓"),
        ("NNØ", "↙"),
        ("NØ", "↙"),
        ("ØNØ", "↙"),
        ("Ø", "←"),
        ("ØSØ", "↖"),
        ("SØ", "↖"),
        ("SSØ", "↖"),
        ("S", "↑"),
        ("SSV", "↗"),
        ("SV", "↗"),
        ("VSV", "↗"),
        ("V", "→"),
        ("VNV", "↘"),
        ("NV", "↘"),
        ("NNV", "↘"),
    ]
    # Hver av de 16 sektorene dekker 22.5 grader.
    indeks = int((grader + 11.25) % 360 // 22.5)
    return retninger[indeks]


class VaerCache:
    """Håndterer lesing, skriving og caching av værdata til disk."""

    def __init__(self, cache_sti: Path = WEATHER_CACHE_FILE):
        self.cache_sti = cache_sti
        self._data: dict[str, dict[str, Any]] = self._last_fra_disk()

    def _last_fra_disk(self) -> dict[str, dict[str, Any]]:
        if not self.cache_sti.is_file():
            return {}
        try:
            with open(self.cache_sti, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _lagre_til_disk(self) -> None:
        try:
            with open(self.cache_sti, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @staticmethod
    def _lag_nokkel(lat: float, lon: float) -> str:
        # Avrund koordinatene til 3 desimaler (~100m presisjon) for god gjenbruk
        return f"{lat:.3f},{lon:.3f}"

    def hent_vaer(self, lat: float, lon: float) -> VaerObservasjon | None:
        nokkel = self._lag_nokkel(lat, lon)
        innslag = self._data.get(nokkel)
        if not innslag:
            return None

        # Sjekk gyldighetstid
        try:
            hentet_tid = arrow.get(innslag["hentet_tid_iso"])
            alder_sekunder = (arrow.now() - hentet_tid).total_seconds()
            if alder_sekunder > WEATHER_CACHE_DURATION_SECONDS:
                return None
            return VaerObservasjon(**innslag)
        except Exception:
            return None

    def lagre_vaer(self, lat: float, lon: float, vaer: VaerObservasjon) -> None:
        nokkel = self._lag_nokkel(lat, lon)
        self._data[nokkel] = {
            "temperatur_c": vaer.temperatur_c,
            "vind_ms": vaer.vind_ms,
            "vindkast_ms": vaer.vindkast_ms,
            "vindretning_grader": vaer.vindretning_grader,
            "vindretning_tekst": vaer.vindretning_tekst,
            "vind_pil": vaer.vind_pil,
            "symbol_kode": vaer.symbol_kode,
            "beskrivelse": vaer.beskrivelse,
            "symbol_emoji": vaer.symbol_emoji,
            "hentet_tid_iso": vaer.hentet_tid_iso,
        }
        self._lagre_til_disk()


vaer_cache = VaerCache()


def parse_symbol_kode(raw_code: str) -> tuple[str, str]:
    """Deler f.eks. 'clearsky_day' inn i ('☀️', 'Klarvær')."""
    base_code = raw_code.split("_")[0]
    if base_code in VAER_SYMBOLER:
        return VAER_SYMBOLER[base_code]
    for key, val in VAER_SYMBOLER.items():
        if key in raw_code:
            return val
    return ("🌡️", raw_code.capitalize())


def hent_vaer_fra_met(
    session: requests.Session, lat: float, lon: float
) -> VaerObservasjon | None:
    """Henter ferske værdata fra MET hvis cachen er utgått."""
    cached = vaer_cache.hent_vaer(lat, lon)
    if cached is not None:
        return cached

    client_id = str(config.get("etClientName", "avgangstider-entur-python"))
    user_agent = f"{client_id} (kontakt: github.com/avgangstider)"

    headers = {
        "User-Agent": user_agent,
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
            return None

        body = res.json()
        now_timeseries = body["properties"]["timeseries"][0]["data"]
        instant = now_timeseries["instant"]["details"]
        temp = instant.get("air_temperature", 0.0)
        vind = instant.get("wind_speed", 0.0)
        vindkast_raw = instant.get("wind_speed_of_gust")
        vindkast = float(vindkast_raw) if vindkast_raw is not None else None
        vindretning = float(instant.get("wind_from_direction", 0.0))

        vind_tekst, vind_pil = grader_til_vindretning(vindretning)

        next_1h = now_timeseries.get("next_1_hours") or now_timeseries.get("next_6_hours") or {}
        summary = next_1h.get("summary", {})
        raw_symbol = summary.get("symbol_code", "clearsky")

        emoji, beskrivelse = parse_symbol_kode(raw_symbol)

        observasjon = VaerObservasjon(
            temperatur_c=float(temp),
            vind_ms=float(vind),
            vindkast_ms=vindkast,
            vindretning_grader=vindretning,
            vindretning_tekst=vind_tekst,
            vind_pil=vind_pil,
            symbol_kode=raw_symbol,
            beskrivelse=beskrivelse,
            symbol_emoji=emoji,
            hentet_tid_iso=arrow.now().isoformat(),
        )

        vaer_cache.lagre_vaer(lat, lon, observasjon)
        return observasjon
    except Exception:
        return None


# ==============================================================================
# INNLESING AV FILER OG OPPSETT
# ==============================================================================
def last_inn_stoppesteder(filsti: Path | None = None) -> dict[str, dict[str, str]]:
    """
    Leser inn stoppesteder fra fil, inndelt i seksjoner (f.eks. [hjem], [jobb]).
    Returnerer en dict av profiler: {'hjem': {...}, 'jobb': {...}, ...}
    """
    if filsti is None:
        filsti = BASE_DIR / "stoppesteder.txt"

    if not filsti.is_file():
        print(f"Feil: Fant ikke stoppesteder-filen på: {filsti}")
        print("Du må opprette filen 'stoppesteder.txt' og legge stoppestedene der.")
        print("Se på 'stoppesteder_eksempel.txt' for hvordan filen skal se ut.")
        print("Du kan finne stoppesteder på https://stoppesteder.entur.org")
        sys.exit(1)

    profiler: dict[str, dict[str, str]] = {}
    aktiv_profil: str | None = None

    try:
        with open(filsti, "r", encoding="utf-8") as f:
            for linjenr, linje in enumerate(f, start=1):
                linje = linje.strip()

                if not linje or linje.startswith("#"):
                    continue

                if linje.startswith("[") and linje.endswith("]"):
                    aktiv_profil = linje[1:-1].strip().lower()
                    if not aktiv_profil:
                        print(f"Feil på linje {linjenr} i {filsti}: Tom seksjon '[]'.")
                        sys.exit(1)
                    if aktiv_profil not in profiler:
                        profiler[aktiv_profil] = {}
                    continue

                if "=" not in linje:
                    continue

                if aktiv_profil is None:
                    print(f"Feil i {filsti}: Stoppesteder må plasseres under en seksjon (f.eks. [hjem] eller [jobb]).")
                    print(f"Linje {linjenr}: '{linje}' mangler overskrift/seksjon.")
                    sys.exit(1)

                navn, nsr_id = linje.split("=", 1)
                ren_navn = navn.strip().strip('"').strip("'")
                ren_id = nsr_id.strip().strip('"').strip("'")

                profiler[aktiv_profil][ren_navn] = ren_id

        if not profiler:
            print(f"Ingen profiler/seksjoner funnet i {filsti}.")
            print("Definer minst én seksjon med stoppesteder, f.eks.:")
            print('[hjem]\nOlaf Ryes plass = "NSR:StopPlace:6433"')
            sys.exit(1)

        return profiler
    except OSError as e:
        print(f"Feil under lesing av {filsti}: {e}")
        sys.exit(1)


# ==============================================================================
# HJELPEFUNKSJONER FOR FORMATERING OG TID
# ==============================================================================
def minutter_til_avgang(expected_iso_str: str) -> str:
    """Regner ut hvor mange minutter det er til avgang, basert på sanntid."""
    forventet_tid = arrow.get(expected_iso_str)
    naa = arrow.now(forventet_tid.tzinfo)
    differanse_sekunder = (forventet_tid - naa).total_seconds()
    minutter_igjen = int(differanse_sekunder // 60)

    if minutter_igjen <= 0:
        return "Nå"
    elif minutter_igjen == 1:
        return "1 min"
    else:
        return f"{minutter_igjen} min"


def formater_transportmodus(transport_mode: str | None) -> str:
    """Returnerer transportmiddelet tilpasset valgt terminalstil."""
    mode_key = (transport_mode or "").lower()

    match TERM_MODE:
        case TermStil.MODERNE:
            emoji, tekst = TRANSPORT_MODERNE.get(mode_key, ("🚏", mode_key.capitalize() or "Ukjent"))
            return f"{emoji} {tekst:<6}"
        case _:
            tekst = TRANSPORT_KLASSISK.get(mode_key, mode_key.capitalize() or "Ukjent")
            return f"{tekst:<6}"


def formater_forsinkelse_moderne(forsinkelse_minutter: int) -> str:
    if forsinkelse_minutter > 0:
        return f"🔴 {forsinkelse_minutter} min forsinket"
    elif forsinkelse_minutter < 0:
        return f"💚 {abs(forsinkelse_minutter)} min tidlig"
    else:
        return "💚 I rute"


def formater_forsinkelse_klassisk(forsinkelse_minutter: int) -> str:
    red = "\033[91m"
    green = "\033[92m"
    reset = "\033[0m"

    if forsinkelse_minutter > 0:
        return f"{red}[!] {forsinkelse_minutter} min forsinket{reset}"
    elif forsinkelse_minutter < 0:
        return f"{green}[+] {abs(forsinkelse_minutter)} min tidlig{reset}"
    else:
        return f"{green}[V] I rute{reset}"


def formater_forsinkelse(aimed_raw: str, expected_raw: str) -> str:
    aimed = arrow.get(aimed_raw)
    expected = arrow.get(expected_raw)
    tidsdifferanse = (expected - aimed).total_seconds()
    forsinkelse_minutter = int(tidsdifferanse // 60)

    match TERM_MODE:
        case TermStil.MODERNE:
            return formater_forsinkelse_moderne(forsinkelse_minutter)
        case _:
            return formater_forsinkelse_klassisk(forsinkelse_minutter)


def iso_til_normaltid(time_str: str, format_str: str = "HH:mm") -> str:
    return arrow.get(time_str).format(format_str)


def toem_terminal() -> None:
    command = "cls" if sys.platform.startswith("win") else "clear"
    try:
        subprocess.run([command], check=True)
    except Exception:
        pass


# ==============================================================================
# ENTUR GRAPHQL API KOMMUNIKASJON
# ==============================================================================
def construct_stop_place_query(
    nsr_stop_place_id: str,
    time_range_seconds: int = DEFAULT_TIME_RANGE_SECONDS,
    departures_count: int = DEFAULT_DEPARTURES_COUNT,
) -> str:
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
          actualArrivalTime
          actualDepartureTime
          date
          forBoarding
          forAlighting
          destinationDisplay {
            frontText
          }
          quay {
            id
          }
          serviceJourney {
            journeyPattern {
              line {
                id
                name
                publicCode
                transportMode
              }
            }
          }
        }
      }
    }
    """
    query_template = Template(textwrap.dedent(raw_template).strip())
    return query_template.substitute(
        nsr_id=nsr_stop_place_id,
        time_range=time_range_seconds,
        num_departures=departures_count,
    )


def send_graphql_query(session: requests.Session, query: str) -> dict[str, Any]:
    """Sender GraphQL-forespørsel til Entur med timeout og feilsjekk."""
    headers = {"ET-Client-Name": str(config.get("etClientName", "avgangstider-cli"))}
    body = {"query": query}

    response = session.post(
        ENTUR_GRAPHQL_URL,
        headers=headers,
        json=body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise requests.HTTPError(
            f"Entur API returnerte HTTP {response.status_code}: {response.text[:120]}"
        )

    data = response.json()
    if "errors" in data and not data.get("data"):
        feilmeldinger = "; ".join(e.get("message", "Ukjent feil") for e in data["errors"])
        raise ValueError(f"GraphQL-feil: {feilmeldinger}")

    return data


def hent_og_oppdater_avgangsinfo(
    session: requests.Session,
    stoppesteder_tilstand: dict[str, StoppestedData],
    time_range_seconds: int,
    departures_count: int,
) -> None:
    """Henter nye data fra Entur for hvert stoppested, og oppdaterer vær via MET."""
    for alias_navn, tilstand in stoppesteder_tilstand.items():
        graphql_query = construct_stop_place_query(
            tilstand.nsr_id,
            time_range_seconds=time_range_seconds,
            departures_count=departures_count,
        )
        try:
            data = send_graphql_query(session, graphql_query)
            stop_info = data.get("data", {}).get("stopPlace")
            if stop_info:
                tilstand.response = data
                tilstand.feilmelding = None
                tilstand.sist_oppdatert = arrow.now()

                lat = stop_info.get("latitude")
                lon = stop_info.get("longitude")
                if lat is not None and lon is not None:
                    tilstand.latitude = float(lat)
                    tilstand.longitude = float(lon)
                    # Hent eller oppdater vær
                    tilstand.vaer = hent_vaer_fra_met(session, tilstand.latitude, tilstand.longitude)
            else:
                tilstand.feilmelding = f"Ingen data funnet for ID {tilstand.nsr_id}"
        except (requests.RequestException, ValueError, Exception) as e:
            tilstand.feilmelding = str(e)


# ==============================================================================
# UTSKRIFT OG VISNING
# ==============================================================================
def lag_terminal_lenke(url: str, tekst: str) -> str:
    """Pakker inn tekst i en OSC 8 ANSI-sekvens slik at teksten blir en klikkbar lenke i terminalen."""
    return f"\033]8;;{url}\033\\{tekst}\033]8;;\033\\"


def formater_vaer_streng(vaer: VaerObservasjon | None) -> str:
    """Formaterer vær-teksten for overskriften inkludert vindretning, grader og kastvind."""
    if not vaer:
        return ""

    # Vind-tekst med eventuelt kastvind (f.eks. "7.2 (12.4) m/s")
    if vaer.vindkast_ms and vaer.vindkast_ms > vaer.vind_ms:
        vind_tall = f"{vaer.vind_ms:.1f} ({vaer.vindkast_ms:.1f}) m/s"
    else:
        vind_tall = f"{vaer.vind_ms:.1f} m/s"

    grader_heltall = int(round(vaer.vindretning_grader))

    if TERM_MODE == TermStil.MODERNE:
        return (
            f" ({vaer.symbol_emoji} {vaer.temperatur_c:.0f}°C, {vaer.beskrivelse}, "
            f"💨 {vind_tall} {vaer.vind_pil} {vaer.vindretning_tekst} {grader_heltall}°)"
        )
    else:
        return (
            f" ({vaer.temperatur_c:.0f}C, {vaer.beskrivelse}, "
            f"{vind_tall} {vaer.vindretning_tekst} {grader_heltall}deg)"
        )


def render_stoppested(alias_navn: str, tilstand: StoppestedData, terminal_width: int) -> None:
    """Viser avgangene for et gitt stoppested i terminalen."""
    har_ferske_data = tilstand.feilmelding is None and tilstand.response is not None
    stop_data = tilstand.response.get("data", {}).get("stopPlace") if tilstand.response else None

    # Bruk offisielt navn fra API hvis tilgjengelig, ellers brukerens alias
    visningsnavn = stop_data.get("name") if stop_data and stop_data.get("name") else alias_navn
    vaer_tekst = formater_vaer_streng(tilstand.vaer)

    # Bygg Yr-lenke hvis koordinater er tilgjengelige
    yr_url: str | None = None
    if tilstand.latitude is not None and tilstand.longitude is not None:
        yr_url = f"https://www.yr.no/nb/værvarsel/daglig-tabell/{tilstand.latitude:.4f},{tilstand.longitude:.4f}"

    if yr_url and TERM_MODE == TermStil.MODERNE:
        # Gjør selve visningsnavnet og pin-ikonet klikkbart
        klikkbart_navn = lag_terminal_lenke(yr_url, visningsnavn)
        klikkbar_pin = lag_terminal_lenke(yr_url, "📍")
        # Regn ut fyll-lengde basert på ren synlig tekst (uten ANSI-koder)
        synlig_lengde = len(f" {visningsnavn}{vaer_tekst} ")
        side_streker = max(1, (terminal_width - synlig_lengde) // 2)
        venstre = "-" * side_streker
        hoyre = "-" * (terminal_width - synlig_lengde - side_streker)
        print(f"{venstre} {klikkbart_navn}{vaer_tekst} {hoyre}{klikkbar_pin}")
    else:
        header_tekst = f" {visningsnavn}{vaer_tekst} "
        print(f"{header_tekst:-^{terminal_width}}📍")

    # Hvis vi har en feilmelding:
    if tilstand.feilmelding:
        if tilstand.response and tilstand.sist_oppdatert:
            sist_tid = tilstand.sist_oppdatert.format("HH:mm:ss")
            print(f"⚠️  Kunne ikke hente ferske data ({tilstand.feilmelding}). Viser gamle data fra kl. {sist_tid}:")
        else:
            print(f"❌ Kunne ikke hente data for {visningsnavn}: {tilstand.feilmelding}")
            return

    if not stop_data:
        print("  Ingen data tilgjengelig.")
        return

    estimated_calls = stop_data.get("estimatedCalls") or []
    if not estimated_calls:
        print("  Ingen planlagte avganger i valgt tidsvindu.")
        return

    for call in estimated_calls:
        line_info = call.get("serviceJourney", {}).get("journeyPattern", {}).get("line", {})
        linje_nr = line_info.get("publicCode") or "?"
        modus_str = formater_transportmodus(line_info.get("transportMode"))
        destinasjon = call.get("destinationDisplay", {}).get("frontText") or "Ukjent"

        planlagt_avgang_iso = call.get("aimedDepartureTime") or call.get("aimedArrivalTime")
        forventet_avgang_iso = call.get("expectedDepartureTime") or call.get("expectedArrivalTime")

        if not planlagt_avgang_iso or not forventet_avgang_iso:
            continue

        planlagt_klokke = iso_til_normaltid(planlagt_avgang_iso)
        forventet_klokke = iso_til_normaltid(forventet_avgang_iso)

        if har_ferske_data:
            tid_til_avgang = minutter_til_avgang(forventet_avgang_iso)
            forsinkelse = formater_forsinkelse(planlagt_avgang_iso, forventet_avgang_iso)

            if call.get("realtime"):
                print(
                    f"{modus_str} {linje_nr:<5} {destinasjon:33}  "
                    f"{tid_til_avgang:6}  {forventet_klokke} ({planlagt_klokke}) -- {forsinkelse:18}"
                )
            else:
                tid_til_planlagt = minutter_til_avgang(planlagt_avgang_iso)
                print(
                    f"{modus_str} {linje_nr:<5} {destinasjon:33}  "
                    f"{tid_til_planlagt:6}  {planlagt_klokke} -- mangler sanntidsdata"
                )
        else:
            # Hvis vi IKKE fikk 200 OK: Vis kun klokkeslett, ikke usikre minutt-nedtellinger
            print(
                f"{modus_str} {linje_nr:<5} {destinasjon:33}  "
                f"Klokke: {forventet_klokke} (planlagt: {planlagt_klokke}) [frakoblet]"
            )


def generer_kommandolinje_argumenter(alle_profiler: dict[str, dict[str, str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vis avgangstider for kollektivtransport fra Entur med værdata fra MET/Yr.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    gruppe = parser.add_mutually_exclusive_group()
    for index, profil_navn in enumerate(alle_profiler.keys()):
        hjelpetekst = f"Vis stoppesteder for '{profil_navn}'"
        if index == 0:
            hjelpetekst += " (standard)"
        gruppe.add_argument(
            f"--{profil_navn}",
            dest="profil",
            action="store_const",
            const=profil_navn,
            help=hjelpetekst,
        )

    parser.add_argument(
        "posisjonell_profil",
        nargs="?",
        default=None,
        help="Valgfri profil / sted (f.eks. 'hjem' eller 'uit')",
    )

    parser.add_argument(
        "--timerange",
        type=int,
        default=DEFAULT_TIME_RANGE_SECONDS,
        help=f"Hvor mange sekunder frem i tid det skal letes etter avganger (standard: {DEFAULT_TIME_RANGE_SECONDS}s = {DEFAULT_TIME_RANGE_SECONDS//60}m)",
    )

    parser.add_argument(
        "--antall",
        type=int,
        default=DEFAULT_DEPARTURES_COUNT,
        help=f"Maksimalt antall avganger per stoppested (standard: {DEFAULT_DEPARTURES_COUNT})",
    )

    parser.add_argument(
        "--intervall",
        type=int,
        default=DEFAULT_REFRESH_INTERVAL_SECONDS,
        help=f"Oppdateringsintervall i sekunder (standard: {DEFAULT_REFRESH_INTERVAL_SECONDS}s)",
    )

    return parser.parse_args()


# ==============================================================================
# HOVEDFUNKSJON OG ARGUMENT-PARSING
# ==============================================================================
def main() -> None:
    global config

    # 1. Valider og last inn .env-konfigurasjon
    env_sti = BASE_DIR / ".env"
    if not env_sti.is_file():
        print(f"Feil: Fant ikke konfigurasjonsfilen: {env_sti}")
        print("Du må opprette en '.env'-fil i prosjektmappen basert på '.env_example'.")
        print("Eksempel:")
        print("  cp .env_example .env")
        print('  echo \'etClientName="mittnavn-avgangstider-$(shuf -i 1000-9999 -n 1)"\' > .env')
        sys.exit(1)

    config = dotenv_values(env_sti)
    if not config or "etClientName" not in config or not config["etClientName"]:
        print(f"Feil: Mangler gyldig 'etClientName' i {env_sti}")
        print("Filen må inneholde en unik identifikator på formen:")
        print('etClientName="<company>-<application>"')
        sys.exit(1)

    # 2. Last inn stoppesteder og profiler (validerer også at stoppesteder.txt finnes)
    alle_profiler = last_inn_stoppesteder()
    args = generer_kommandolinje_argumenter(alle_profiler)

    # 4. Velg profil
    valgt_profil = args.profil or (args.posisjonell_profil.lower() if args.posisjonell_profil else None)

    if valgt_profil:
        if valgt_profil not in alle_profiler:
            tilgjengelige = ", ".join(f"'{p}'" for p in alle_profiler)
            print(f"Feil: Profil '{valgt_profil}' finnes ikke i stoppesteder.txt.")
            print(f"Tilgjengelige profiler: {tilgjengelige}")
            sys.exit(1)
        aktive_stoppesteder = alle_profiler[valgt_profil]
    else:
        foerste_profil = next(iter(alle_profiler.keys()))
        aktive_stoppesteder = alle_profiler[foerste_profil]

    if not aktive_stoppesteder:
        print("Ingen stoppesteder funnet for valgt profil.")
        sys.exit(1)

    # 5. Klargjør tilstandsobjekter per stoppested
    tilstander: dict[str, StoppestedData] = {
        navn: StoppestedData(navn=navn, nsr_id=nsr_id)
        for navn, nsr_id in aktive_stoppesteder.items()
    }

    session = requests.Session()
    toem_terminal()

    # 6. Hovedløkke
    while True:
        print("Henter avgangsinfo...")
        hent_og_oppdater_avgangsinfo(
            session=session,
            stoppesteder_tilstand=tilstander,
            time_range_seconds=args.timerange,
            departures_count=args.antall,
        )

        toem_terminal()

        for tilstand in tilstander.values():
            render_stoppested(tilstand.navn, tilstand, DEFAULT_TERMINAL_WIDTH)

        print("=" * (DEFAULT_TERMINAL_WIDTH + 1))
        time.sleep(args.intervall)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAvslutter...")
        sys.exit(0)
