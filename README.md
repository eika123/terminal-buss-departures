# Avgangstider fra Entur

Dette prosjektet henter sanntids avgangstider for kollektivtransport (buss, trikk, tog, metro, båt) via Enturs offentlige JourneyPlanner GraphQL API, henter lokalt vær for stoppestedet fra Meteorologisk institutt (MET / Yr), og viser alt pent formatert i terminalen med farger og symboler.

---

## Egenskaper

- **Sanntid og forsinkelser**: Viser nøyaktig minutt-nedtelling og avvik fra rutetabellen.
- **Lokalt vær**: Henter automatisk temperatur, vind og værsymbol fra Meteorologisk institutt (Locationforecast 2.0) basert på holdeplassens geografiske koordinater.
- **Lokal disk-cache for vær**: Værdata caches til disk (`.weather_cache.json`) i 30 minutter, slik at MET-serverne skånes selv om du restarter appen hyppig.
- **Feiltolerant**: Ved nettverksbrudd eller feil hos Entur/MET krasjer ikke appen, men viser forrige kjente avganger med en tydelig frakoblet-advarsel.
- **Profiler og seksjoner**: Grupper stoppesteder etter f.eks. `[hjem]`, `[jobb]` og `[uit]`, og bytt enkelt med kommandolinjeflagg som `--hjem` eller posisjonelt argument `hjem`.
- **Globalt CLI-verktøy**: Kan installeres direkte i PATH med `uv tool install --editable .`.

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

### 2. Konfigurer Entur Client ID (`.env`)

Enturs API krever en unik identifikator for klienten som sender forespørsler, i formatet:
`<company>-<application>`

1. Opprett en `.env`-fil basert på `.env_example`:
   ```bash
   cp .env_example .env
   ```

2. Generer et tilfeldig tall (for eksempel ved hjelp av `shuf` i bash) for å gi applikasjonen et unikt navn:
   ```bash
   echo "etClientName=\"mittnavn-avgangstider-$(shuf -i 1000-9999 -n 1)\"" > .env
   ```
   Eller åpne `.env` i en teksteditor og sett inn verdien manuelt, for eksempel:
   ```dotenv
   etClientName="mittnavn-avgangstider4821"
   ```

---

### 3. Konfigurer stoppesteder (`stoppesteder.txt`)

Filen `stoppesteder.txt` **må** være inndelt i seksjoner med hakeparenteser (`[...]`). Den **øverste seksjonen** i filen blir automatisk brukt som standard når du kjører programmet uten argumenter.

1. Gå til [stoppesteder.entur.org](https://stoppesteder.entur.org/) og søk opp stoppestedene dine for å finne `NSR:StopPlace`-ID-en (f.eks. `NSR:StopPlace:58366`).
2. Opprett eller rediger `stoppesteder.txt` (se `stoppesteder_eksempel.txt` for referanse):
   ```ini
   # Den første/øverste seksjonen er standard (f.eks. [hjem])
   [hjem]
   Klimavegen = "NSR:StopPlace:53434"
   Workinnmarka skole = "NSR:StopPlace:53105"

   [jobb]
   Forskningsparken = "NSR:StopPlace:9912"

   [biblioteket]
   Kulturhuset = "NSR:StopPlace:5511"
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

