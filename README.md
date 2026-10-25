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
destination_max_width = 50   # Truncates destination text to keep time columns aligned
terminal_width = 95          # Header and border line width
terminal_style = "modern"    # "modern" (colors/emojis) or "classic" (ASCII)
language = "en"

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
| 🇫🇮 **Helsinki (Finland)** | Digitransit / HSL | **Supported (HSL tested)** | [reittiopas.hsl.fi](https://reittiopas.hsl.fi/) (click on a stop to view URL/code) or [digitransit.fi](https://digitransit.fi/) | `HSL:1040101` / `1040101` |
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

[helsinki]
Rautatientori = "HSL:1040101"
Kamppi = "HSL:1020455"
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

### Static Analysis & Security Scanning

To run the static analysis pipeline independently:

```bash
# Runs Pyflakes, Ruff, Bandit security scan, and Pydeps cycle detection:
./scripts/run-static-analysis.sh

# Pass --doc to also generate visual dependency diagrams in static-analysis/:
./scripts/run-static-analysis.sh --doc
```

Included tools:
- **[Ruff](https://astral.sh/ruff)**: Fast code linting and style formatting.
- **[Pyflakes](https://pypi.org/project/pyflakes/)**: Fast logical analysis (detects unused imports, undefined variables, and scope errors).
- **[Bandit](https://bandit.readthedocs.io/)**: Security scanner that detects leaked secrets, hardcoded credentials, and unsafe function invocations.
- **[Pydeps](https://github.com/thebjorn/pydeps)**: Dependency graph verification and cycle detection (verifies that the architecture is a clean DAG). Generates `static-analysis/dependencies.svg` and `static-analysis/dependencies.json` when invoked with `--doc`.
- **[Pytest](https://docs.pytest.org/)**: Unit test suite (`uv run pytest -v`).

---

## License

This project is licensed under the [GNU General Public License v3.0 (GPL-3.0)](LICENSE).
