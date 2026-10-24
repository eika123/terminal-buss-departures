# Avgangstider fra Entur

Dette prosjektet henter sanntids avgangstider for kollektivtransport (buss, trikk, tog, etc.) via Enturs offentlige JourneyPlanner GraphQL API og viser dem pent formatert i terminalen.

> **Merk:** Applikasjonen er per i dag kun testet på bussruter i Tromsø.

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

Du må spesifisere hvilke stoppesteder du ønsker å overvåke:

1. Gå til [stoppesteder.entur.org](https://stoppesteder.entur.org/) og søk opp stoppestedene dine for å finne `NSR:StopPlace`-ID-en (f.eks. `NSR:StopPlace:58366`).
2. Opprett filen `stoppesteder.txt` (se `stoppesteder_eksempel.txt` for referanse):
   ```text
   Jernbanetorget = "NSR:StopPlace:58366"
   Stortorvet = "NSR:StopPlace:4160"
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

