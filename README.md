# Avgangstider / Departure Board (Nordic Transit)

Dette prosjektet henter sanntids avgangstider for kollektivtransport (buss, trikk, tog, metro, båt) via Enturs JourneyPlanner GraphQL API, henter lokalt vær for stoppestedet fra Meteorologisk institutt (MET / Yr), og viser alt pent formatert i terminalen med farger og symboler.

Kildekoden er refaktorert med engelske funksjonsnavn, standard logging til fil (`avgangstider.log`), og støtter flere språk i brukergrensesnittet (**norsk**, **svensk**, **finsk** og **engelsk**).

---

## Egenskaper

- **Flerspråklig (i18n)**: Støtter norsk (`no`), svensk (`sv`), finsk (`fi`) og engelsk (`en`) med `--lang fi` eller `LANGUAGE=fi` i `.env`.
- **Sanntid og forsinkelser**: Viser nøyaktig minutt-nedtelling og avvik fra rutetabellen.
- **Lokalt vær og vindretning**: Henter automatisk temperatur, vind, kastvind, 16-dels kompassretning og grader fra Meteorologisk institutt (Locationforecast 2.0).
- **Klikkbare lenker**: Klikk direkte på holdeplassen eller pin-ikonet for å åpne værmeldingen på Yr.no (via OSC 8 hyperlinks).
- **Lokal disk-cache for vær**: Værdata caches til disk (`.weather_cache.json`) i 30 minutter.
- **Feiltolerant**: Ved nettverksbrudd krasjer ikke appen, men viser forrige kjente avganger med et diskret `📡`-varsel.
- **Profiler og seksjoner**: Grupper stoppesteder etter f.eks. `[hjem]`, `[jobb]`, og bytt enkelt med `--hjem` eller posisjonelt argument `hjem`.
- **Globalt CLI-verktøy**: Kan installeres direkte i PATH med `uv tool install --editable .`.

---

## Kjøring og språkflagg

```bash
# Standard visning (norsk)
avgangstider

# Visning på finsk
avgangstider --lang fi

# Visning på svensk
avgangstider --lang sv

# Med spesifikk seksjon og språk:
avgangstider --hjem --lang fi
# eller:
avgangstider hjem --lang sv
```

---

## Forutsetninger

- Python 3.14+ (eller installert via [uv](https://github.com/astral-sh/uv))
- Avhengigheter: `requests`, `python-dotenv`, `arrow`

Har du `uv` installert, håndteres avhengigheter automatisk med `uv run`.

---

## Installasjon og oppsett

### 1. Klon prosjektet og installer avhengigheter

Ved bruk av `uv`:
```bash
uv sync
```

Eller med standard `pip` og virtuelt miljø:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests python-dotenv arrow
```

---

### 2. Konfigurer miljøvariabler (`.env`)

Opprett en `.env`-fil i prosjektmappen basert på `.env_example`:

```dotenv
# 1. Meteorologisk institutt (påkrevd for værdata i alle land)
# MET krever at du identifiserer deg med appnavn og din egen kontakt-e-post/URL:
MET_USER_AGENT="MyTransitBoard/1.0 (contact: din-epost@example.com)"

# 2. Norge / Entur (påkrevd KUN hvis du bruker norske stoppesteder)
# Format: <company>-<application>
ET_CLIENT_NAME="mittnavn-avgangstider-4821"

# 3. Finland / Digitransit (påkrevd KUN hvis du bruker finske stoppesteder)
# Gratis API-nøkkel fra: https://digitransit.fi/en/developers/api-registration/
DIGITRANSIT_SUBSCRIPTION_KEY="din-digitransit-nokkel"

# 4. Valgfritt: Standardspråk ('no', 'sv', 'fi', 'en')
LANGUAGE="no"
```

---

### 3. Konfigurer stoppesteder (`stoppesteder.txt`)

Filen `stoppesteder.txt` **må** være inndelt i seksjoner med hakeparenteser (`[...]`). Den **øverste seksjonen** i filen blir automatisk brukt som standard når du kjører programmet uten argumenter.

#### Hvor finner du stoppesteder og ID-er i Norden?

| Land | Tjeneste | Hvor finner du stoppesteder / ID | Eksempel på ID |
| :--- | :--- | :--- | :--- |
| 🇳🇴 **Norge** | Entur (NSR) | [stoppesteder.entur.org](https://stoppesteder.entur.org/) | `NSR:StopPlace:58366` |
| 🇫🇮 **Finland** | Digitransit / HSL | [reittiopas.hsl.fi](https://reittiopas.hsl.fi/) (klikk på holdeplass og se URL/tallkode) eller [digitransit.fi](https://digitransit.fi/) | `HSL:1040101` / `1040101` |
| 🇸🇪 **Sverige** | Trafiklab (ResRobot) | [trafiklab.se/api/resrobot-v21/](https://www.trafiklab.se/) eller [sl.se](https://sl.se/) (stoppestedskoder / EVA-nummer) | `740000001` (Stockholm C) |
| 🇩🇰 **Danmark** | Rejseplanen | [labs.rejseplanen.dk](https://labs.rejseplanen.dk/) eller [rejseplanen.dk](https://www.rejseplanen.dk/) (stoppestedsnummer) | `008600611` (København H) |

#### Eksempel på `stoppesteder.txt`:

Opprett eller rediger `stoppesteder.txt` (se `stoppesteder_eksempel.txt` for referanse):
```ini
# Den første/øverste seksjonen er standard (f.eks. [hjem])
[hjem]
Klimavegen = "NSR:StopPlace:53434"
Workinnmarka skole = "NSR:StopPlace:53105"

[jobb]
Forskningsparken = "NSR:StopPlace:9912"

[helsinki]
Rautatientori = "HSL:1040101"
Kamppi = "HSL:1020455"

[stockholm]
T-Centralen = "740000001"

[kobenhavn]
København H = "008600611"
```

---

## Kjøring og profiler

Applikasjonen leser seksjonene i `stoppesteder.txt` dynamisk og lager tilsvarende kommandolinjeargumenter og `--help`-oversikt:

### Eksempler på kjøring:

```bash
# Viser stoppestedene fra den ØVERSTE seksjonen i stoppesteder.txt (f.eks. [hjem])
avgangstider

# Viser eksplisitt stoppesteder for [hjem]
avgangstider --hjem
# eller posisjonelt:
avgangstider hjem

# Viser stoppesteder for [jobb]
avgangstider --jobb
# eller posisjonelt:
avgangstider jobb

# Se tilgjengelige profiler og hjelpetekst
avgangstider --help
```

---

## Kjøring og installasjon

### Alternativ A: Kjør direkte med `uv` (fra prosjektmappen)

```bash
uv run avgangstider.py
```

### Alternativ B: Installer som globalt CLI-verktøy med `uv tool`

Du kan installere kommandoen direkte inn i PATH (`~/.local/bin/avgangstider`) slik at den kan kjøres fra hvilken som helst mappe på maskinen:

```bash
# Installer lokalt i editable-modus fra prosjektmappen:
uv tool install --editable .
```

Deretter kan du starte programmet hvor som helst fra terminalen:
```bash
avgangstider
```

*(Tips: Hvis du oppdaterer koden eller endrer `stoppesteder.txt`, trer endringene i kraft med en gang takket være `--editable`.)*

---

## Lisens

Dette prosjektet er lisensiert under [GNU General Public License v3.0 (GPL-3.0)](LICENSE).

