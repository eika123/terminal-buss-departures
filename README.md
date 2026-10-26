# Nordic Transit Departure Board (avgangstider)

A terminal-based transit departure board that fetches real-time public transit schedules (bus, tram, rail, metro, ferry) in Norway (via Entur GraphQL) and the Helsinki region in Finland (via Digitransit HSL), enriched with local weather observations from the Norwegian Meteorological Institute (MET Norway / Yr).

> **Current Regional Support Note:**
> - 🇳🇴 **Norway**: Fully supported via Entur across all national transit operators.
> - 🇫🇮 **Finland**: Tested and active for the **Helsinki metropolitan region (HSL)**. (National Digitransit routing exists in adapters, but testing has focused on HSL).
> - 🇸🇪 **Sweden** & 🇩🇰 **Denmark**: **Not yet supported**. ID schemes and country detection hooks exist in the code base, but API integrations (ResRobot/Trafiklab and Rejseplanen) require separate API keys and adapter implementations.

The interface is localized in **Norwegian**, **Swedish**, **Finnish**, and **English**, and displays clean, ANSI/color-coded outputs with emoji icons and terminal hyperlinks.

---

## Features

- **Multi-language UI (i18n)**: Native support for Norwegian (`no`), Swedish (`sv`), Finnish (`fi`), and English (`en`) selectable via `--lang <lang>` or `LANGUAGE=<lang>` in `.env` / `config.toml`.
- **Culturally Aware Rapid Transit Naming**: Intelligently identifies metro and tram networks across Nordic and European cities to display culturally authentic local names (endonyms) or visitor exonyms (e.g. Oslo: *T-bane*, Stockholm: *T-bana*, Bergen: *Bybanen*, Tampere: *Nysse* / *Ratikka*, London: *Tube* / *Tuben*, Berlin: *U-Bahn*). Finnish speakers viewing Oslo stations will see *Metro*, and in Bergen *Pikaspora*.
- **Real-time Countdown & Delays**: Accurate minute counts and schedule deviations with aligned status indicators.
- **Local Weather & Wind Direction**: Automatically displays temperature, wind speed, gusts, 16-point localized compass headings, and weather condition emojis from MET Norway Locationforecast 2.0.
- **Interactive Terminal Hyperlinks**: Click directly on stop headers or map pins to view detailed weather forecasts on Yr.no (via OSC 8 terminal hyperlinks).
- **Disk Caching**: Upstream API friendly; weather data is cached locally to disk (`~/.cache/avgangstider/weather_cache.json` or `.weather_cache.json`) for 30 minutes.
- **Network Resilience & Offline Handling**: Gracefully handles network drops using exponential backoff and cached state instead of crashing, with a discrete `📡` offline badge.
- **Named Profiles & Sections**: Group stops into logical contexts such as `[home]`, `[work]`, or `[helsinki]`, and switch between them effortlessly via CLI flags (`--home`) or positional arguments (`avgangstider home`).
- **Global CLI Tool**: Installable directly into your system PATH with `uv tool install --editable .`.

---

## Usage & CLI Flags

> **Note on Running:**
> - To run directly from the repository without installation, prefix commands with `uv run avgangstider` (or `uv run avgangstider.py`).
> - To use `avgangstider` directly as a standalone CLI command anywhere on your system, install it first using `uv tool install --editable .` (see [Global CLI Installation](#global-cli-installation)).

```bash
# Default view (uses the first profile in stoppesteder.txt)
uv run avgangstider
# (or simply 'avgangstider' if installed via uv tool)

# View in Finnish
uv run avgangstider --lang fi

# View in Swedish
uv run avgangstider --lang sv

# View in English
uv run avgangstider --lang en

# Select a specific section and language:
uv run avgangstider --home --lang fi
# Or positionally:
uv run avgangstider home --lang sv
```

---

## Prerequisites

- **Python 3.14+** (managed natively or via [uv](https://github.com/astral-sh/uv))
- Core dependencies: `requests`, `python-dotenv`, `arrow`, `pydantic`

When using `uv`, virtual environments and dependencies are managed automatically.

---

## Installation & Setup

### 1. Clone the repository and install dependencies

Using `uv`:
```bash
uv sync
```

Or using standard Python `venv` and `pip`:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

### 2. Configure Environment Variables (`.env`)

Create a `.env` file in the project directory based on `.env_example`:

```dotenv
# 1. MET Norway (required for weather reports in all countries)
# MET Norway requires clients to identify themselves with an application name and email/URL:
MET_USER_AGENT="MyTransitBoard/1.0 (contact: your-email@example.com)"

# 2. Norway / Entur (required ONLY if querying Norwegian stops)
# Format: <company>-<application>
ET_CLIENT_NAME="myname-departureboard-4821"

# 3. Finland / Digitransit (required ONLY if querying Finnish stops)
# Free API subscription key from: https://digitransit.fi/en/developers/api-registration/
DIGITRANSIT_SUBSCRIPTION_KEY="your-digitransit-key"

# 4. Optional: Default interface language ('no', 'sv', 'fi', 'en')
LANGUAGE="en"
```

---

### 3. Configure Non-Secret Settings (`config.toml`)

Application layout, column widths, lookup time ranges, and styling can be customized in `config.toml`:

```toml
[display]
destination_max_width = 27   # Truncates destination text to keep time columns aligned
transport_mode_max_width = 7 # Truncates long mode names with dot (e.g. Spårvagn -> Spårv.)
terminal_width = 95          # Header and border line width
terminal_style = "modern"    # "modern" (colors/emojis) or "classic" (ASCII)
language = "en"
transit_naming_style = "cultural" # "cultural", "original", or "generic"

# Optional global overrides:
# [display.mode_overrides]
# metro = "T"

# Optional system-specific overrides:
# [display.system_overrides]
# "oslo_ruter.metro" = "T"

[query]
time_range_seconds = 5400    # Lookahead time window (90 minutes)
departures_count = 10        # Maximum departures per stop place
refresh_interval_seconds = 60
```

---

### 4. Configure Stop Places (`stoppesteder.txt`)

The `stoppesteder.txt` file **must** be organized into sections enclosed in square brackets (`[...]`). The **first (top-most) section** is used as the default when running without profile flags.

#### Finding Stop Places & IDs

| Country / Region | Service | Status | Where to Find Stop Places / IDs | Example ID |
| :--- | :--- | :--- | :--- | :--- |
| 🇳🇴 **Norway** | Entur (NSR) | **Supported** | [stoppesteder.entur.org](https://stoppesteder.entur.org/) | `NSR:StopPlace:58366` |
| 🇫🇮 **Helsinki (Finland)** | Digitransit / HSL | **Supported** | [reittiopas.hsl.fi](https://reittiopas.hsl.fi/) (click on a stop to view URL/code) or [digitransit.fi](https://digitransit.fi/) | `fi:hsl:1040101` (or `HSL:1040101`) |
| 🇫🇮 **Tampere (Finland)** | Digitransit / Nysse | **Supported** | [reittiopas.nysse.fi](https://reittiopas.nysse.fi/) or [nysse.fi](https://www.nysse.fi/) (uses Digitransit format) | `fi:nysse:0805` / `fi:tampere:0805` |
| 🇸🇪 **Sweden** | Trafiklab (ResRobot) | *Planned / Not implemented* | [trafiklab.se/api/resrobot-v21/](https://www.trafiklab.se/) | *(Requires API key implementation)* |
| 🇩🇰 **Denmark** | Rejseplanen | *Planned / Not implemented* | [labs.rejseplanen.dk](https://labs.rejseplanen.dk/) | *(Requires API key implementation)* |

#### Example `stoppesteder.txt`:

```ini
# The first section is used by default (e.g. [home])
[home]
Klimavegen = "NSR:StopPlace:53434"
Workinnmarka skole = "NSR:StopPlace:53105"

[work]
Forskningsparken = "NSR:StopPlace:9912"

# Sections support optional comma-separated flags, e.g.:
# - use_normalized_names=true/false
# - transit_naming=cultural/original/generic
[bergen, transit_naming=original]
Byparken = "NSR:StopPlace:59983"

[helsinki, use_normalized_names=false]
Rautatientori = "fi:hsl:1040101"
Kamppi = "fi:hsl:1020455"

[tampere]
Keskustori = "fi:nysse:0805"
Hervantajärvi = "fi:tampere:0824"
```

---

## Profiles & Command Line Arguments

The application parses sections in `stoppesteder.txt` dynamically and generates matching CLI flags and `--help` documentation:

```bash
# View stops from the default (top-most) section in stoppesteder.txt
uv run avgangstider

# View stops explicitly for [home]
uv run avgangstider --home
# Or positionally:
uv run avgangstider home

# View stops for [work]
uv run avgangstider --work

# See all available generated profiles and options
uv run avgangstider --help
```

---

## Culturally Aware Transit Naming & Overrides

Public transit systems (especially metros, trams, and rapid transit) have proud, distinctive local identities. `avgangstider` includes a dedicated transit identities subsystem that automatically recognizes networks by stop ID prefix or geographic coordinates:

| Transit Network | City | Authentic Local Name | Supported Exonyms (by language) |
| :--- | :--- | :--- | :--- |
| **Oslo Ruter** | Oslo, Norway | `T-bane`, `Trikk` | `no`: T-bane / Trikk, `sv`: T-bana / Spårv., `fi`: **Metro** / Ratikka, `en`: T-bane / Tram |
| **Bergen Skyss** | Bergen, Norway | `Bybanen` | `no`: Bybanen, `sv`: Bybanan, `fi`: **Pikaspora**, `en`: Light rail |
| **Trondheim AtB** | Trondheim, Norway | `Gråkallbanen` / `Trikk` | `no`: Gråkallbanen, `sv`: Spårv., `fi`: Ratikka, `en`: Tram |
| **Helsinki HSL** | Helsinki, Finland | `Metro`, `Spora` | `fi`: Metro / Spora, `sv`: Metro / Spårv., `no`: Metro / Trikk, `en`: Metro / Tram |
| **Tampere Nysse** | Tampere, Finland | `Ratikka` (tram) | `fi`: Ratikka, `sv`: Spårv., `no`: Trikk, `en`: Tram |
| **Stockholm SL** | Stockholm, Sweden | `T-bana`, `Spårvagn` | `sv`: T-bana / Spårv., `no`: T-bana / Trikk, `fi`: Metro / Ratikka, `en`: Metro / Tram |
| **London TfL** | London, UK | `Tube` | `en`: Tube, `no`: **Tuben**, `sv`: **Tuben**, `fi`: Metro |
| **Berlin BVG** | Berlin, Germany | `U-Bahn` | `de`/`no`/`sv`/`en`: U-Bahn, `fi`: Metro |

> [!NOTE]
> **Tampere Regional Transit (Nysse & Ratikka):**
> In Tampere, the regional public transport authority and network is **Nysse** ([nysse.fi](https://www.nysse.fi/)), whose journey planner ([reittiopas.nysse.fi](https://reittiopas.nysse.fi/)) uses the same Digitransit GraphQL API schema as Helsinki HSL. Stop IDs from Nysse can be specified with `fi:nysse:` or `fi:tampere:` (or directly `nysse:` / `tampere:`, e.g. `fi:nysse:0805`).

### Naming Modes (`transit_naming_style`)

Configurable globally in `config.toml` or per-profile in `stoppesteder.txt`:

1. **`cultural` (Default)**: Culturally natural naming based on the user's language. A Finnish speaker looking at Oslo stops will see `Metro` instead of the phonetically clunky `T-bane`, while seeing `Pikaspora` for Bergen's Bybane. A Norwegian in London will see `Tuben`.
2. **`original`**: Always displays the authentic local endonym/signage (e.g. `T-bane` in Oslo, `Bybanen` in Bergen, `Tube` in London, `U-Bahn` in Berlin, `Ratikka` in Tampere) even if the UI language is different.
3. **`generic`**: Traditional dictionary translation strictly based on selected UI language.

### Custom User Overrides

Users can override names globally or per-system in `config.toml`:

```toml
[display]
# Set default naming strategy: "cultural", "original", or "generic"
transit_naming_style = "cultural"

# Transport mode column width (longer names automatically truncated with dot):
transport_mode_max_width = 7

# Global mode override:
[display.mode_overrides]
metro = "T"

# System-specific override:
[display.system_overrides]
"oslo_ruter.metro" = "T"
"helsinki_hsl.metro" = "M"
"tampere_nysse.tram" = "Ratikka"
"stockholm_sl.metro" = "T-bana"
```

And per profile in `stoppesteder.txt`:

```ini
[bergen, transit_naming=original]
Byparken = "NSR:StopPlace:59983"
```

---

## Global CLI Installation

Install the application directly into your PATH (`~/.local/bin/avgangstider`) using `uv tool`:

```bash
# Install in editable mode from the repository root:
uv tool install --editable .
```

Now you can run `avgangstider` anywhere on your system. Changes to the code or config take effect immediately.

---

## Quality Assurance, Testing & Static Analysis

Automated tools ensure some minimal code quality and security across the codebase.

### Running All Tests & Analysis

Run the test suite with the consolidated script:

```bash
./scripts/run-tests.sh
```

This runs static analysis checks first and only proceeds to the unit tests if all checks pass (`set -e`).

### Static Analysis, Linting & Security Scanning

To run the static analysis pipeline independently:

```bash
# Runs Pyflakes, Ruff, Pyright, Bandit security scan, and Pydeps cycle detection:
./scripts/run-static-analysis.sh

# Pass --doc to also generate visual dependency diagrams in static-analysis/:
./scripts/run-static-analysis.sh --doc
```

Included tools:
- **[Ruff](https://astral.sh/ruff)**: Fast code linting and style formatting (PEP 8, import sorting, formatting).
- **[Pyright](https://github.com/microsoft/pyright)**: Strict static type checking across models, protocols, and adapters.
- **[Pyflakes](https://pypi.org/project/pyflakes/)**: Fast logical analysis (detects unused imports, undefined variables, and scope errors).
- **[Bandit](https://bandit.readthedocs.io/)**: Security scanner that detects leaked secrets, hardcoded credentials, and unsafe subprocess execution.
- **[Pydeps](https://github.com/thebjorn/pydeps)**: Dependency graph verification and cycle detection (verifies that the architecture is a clean DAG). Generates `static-analysis/dependencies.svg` and `static-analysis/dependencies.json` when invoked with `--doc`.
- **[Pytest](https://docs.pytest.org/)**: Unit, contract, and resilience test suite (`uv run pytest -v`).

### Complexity, Refactoring & AI Telemetry Tools

To maintain clean architecture, keep cognitive complexity low, and support AI-assisted pair programming and refactoring, the project integrates code metrics and telemetry tools:

- **[Radon](https://radon.readthedocs.io/)**: Measures cyclomatic complexity (CC) and maintainability metrics across functions and methods. All modules target Rank A / low B complexity, flagging anything Rank C or worse for refactoring.
- **[Sourcery](https://sourcery.ai/)**: Static refactoring engine that inspects code quality, simplifies loops, extracts guard clauses, optimizes dictionary usage, and eliminates dead code.
- **[Semgrep OSS](https://semgrep.dev/)**: Semantic AST pattern-matching engine detecting code smells, anti-patterns, and architectural issues across the codebase.
- **[pytest-cov](https://pytest-cov.readthedocs.io/)**: Line and branch test coverage measurement ensuring our test coverage remains $\ge 95\%$.

#### Consolidated AI Agent Telemetry Script

To collect all code health and telemetry metrics in one automated step:

```bash
./scripts/run-agent-telemetry.sh
```

This executes Radon, Semgrep, Sourcery, and Pytest coverage in parallel/sequence and generates:
- `.agents/radon_complexity.json`: Cyclomatic complexity scores for all modules.
- `.agents/semgrep_findings.json`: Semantic code pattern findings and anti-patterns.
- `.agents/sourcery_suggestions.csv`: Concrete refactoring suggestions.
- `.agents/coverage.json`: Machine-readable test coverage report.
- `.agents/ai_refactor_prompt.txt`: Synthesized refactoring prompt tailored for AI engineering agents.

### API Contract Testing & Recording (VCR.py)

To guard against unexpected breaking changes from upstream GraphQL and REST APIs (Entur, Digitransit, MET Norway), the test suite includes contract tests recorded with `pytest-recording` (`vcrpy`):

- **Offline Replay by Default**: Everyday runs (`./scripts/run-tests.sh`) replay from recorded cassettes under `tests/cassettes/` in milliseconds without making real network calls.
- **Credential Scrubbing**: Sensitive headers (`ET-Client-Name`, `digitransit-subscription-key`, `User-Agent`) are automatically replaced with dummy placeholders (`DUMMY_...`) so cassettes can be safely committed to git.
- **7-Day TTL (Time-To-Live)**: Cassettes are configured with a 7-day re-record interval (`604800` seconds).
- **Manual Recording Refresh**: To force-refresh and re-record all cassettes against live API endpoints:
  ```bash
  ./scripts/run-tests.sh --record
  ```

#### Scheduled Weekly Refresh (Cron Job)

If you wish to automatically verify API contracts and refresh cassettes on a weekly schedule, you can set up a user cron job:

```bash
# Open crontab editor
crontab -e

# Run tests and re-record weekly every Monday at 06:00 AM:
0 6 * * 1 cd /path/to/avgangstider-entur-python && ./scripts/run-tests.sh --record >> /tmp/avgangstider-contract-tests.log 2>&1
```

### Chaos & Network Resilience Testing

The application is engineered to stay responsive under flaky Wi-Fi and API hiccups:
- **Automatic Retries**: `create_resilient_session()` configures exponential backoff with `urllib3.util.Retry` across transient HTTP status codes (`429`, `500`, `502`, `503`, `504`).
- **Consecutive Failure Tracking**: `ConsecutiveFailureTracker` tolerates intermittent dropped frames, but terminates gracefully after 10 consecutive failures to prevent runaway daemon loops.
- **Offline Cache Preservation**: If network connectivity drops while the board is running, cached departures are preserved on-screen alongside a discrete `📡` offline badge and the last successful sync timestamp.

Resilience and chaos scenarios are verified automatically in `tests/test_resilience.py`.

---

## License

This project is licensed under the [GNU General Public License v3.0 (GPL-3.0)](LICENSE).
