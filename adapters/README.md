# Documentation for certain adapters



## Finland

Finland uses two separate Digitransit GraphQL endpoints:
- **HSL (Helsinki region)**: `https://api.digitransit.fi/routing/v2/hsl/gtfs/v1` (selected with `fi:hsl:<id>`)
- **National (rest of Finland)**: `https://api.digitransit.fi/routing/v2/finland/gtfs/v1` (selected with `fi:<feed>:<id>`)

### Known Feed IDs & Regional Reittiopas

| Town / Region | Digitransit Feed ID | Aliases | Reittiopas (Stop Lookup) | Example in `stoppesteder.txt` |
| :--- | :--- | :--- | :--- | :--- |
| Helsinki (HSL) | `HSL` | `hsl`, `hki` | [reittiopas.hsl.fi](https://reittiopas.hsl.fi/) | `Kamppi = "fi:hsl:1020455"` |
| Tampere | `tampere` | — | [reittiopas.nysse.fi](https://reittiopas.nysse.fi/) | `Keskustori = "fi:tampere:0805"` |
| Turku (Föli) | `FOLI` | `turku`, `foli` | [reittiopas.foli.fi](https://reittiopas.foli.fi/) | `Kristiinankatu = "fi:turku:148"` |
| Oulu | `OULU` | `oulu` | [reittiopas.osl.fi](https://reittiopas.osl.fi/) | `Kauppatori = "fi:oulu:..."` |
| Joensuu | `Joensuu` | `joensuu`, `jojo` | [joensuu.digitransit.fi](https://joensuu.digitransit.fi/) | `Joensuun pääkirjasto I = "fi:joensuu:23575"` |
| Kuopio | `Kuopio` | `kuopio`, `vilkku` | [kuopio.digitransit.fi](https://kuopio.digitransit.fi/) | `Kuopion lentoasema = "fi:kuopio:303023"` |

Any other Digitransit Finland feed ID can be used directly as `fi:<feedId>:<stopId>` without needing an alias. To add a new town or operator alias, add it to `DIGITRANSIT_FEED_ALIASES` in [adapters/digitransit.py](digitransit.py).

### Finding Stop IDs & Feed IDs

- **Stop IDs**: Open your town's Reittiopas (for other cities, search e.g. `"reittiopas <town>"` such as `"reittiopas oulu"`), click on a stop, and copy the stop ID from the end of the URL (after `%3A`, e.g. `.../FOLI%3A148` → `148`).
- **Feed IDs** *(optional)*: To list all available `feedId`s in Digitransit Finland:
  ```bash
  curl -s -X POST https://api.digitransit.fi/routing/v2/finland/gtfs/v1 \
    -H "Content-Type: application/json" \
    -H "digitransit-subscription-key: $DIGITRANSIT_SUBSCRIPTION_KEY" \
    -d '{"query": "{ feeds { feedId } }"}'
  ```

### Adding Stops to `stoppesteder.txt`

Prefix the `gtfsId` with `fi:` under any section in `stoppesteder.txt` (see [example-stop-places/finland.txt](example-stop-places/finland.txt) for a full set of Finnish examples):

```ini
[turku]
Kristiinankatu = "fi:FOLI:148"
# or using the town alias:
Kristiinankatu = "fi:turku:148"
```

Finland uses two separate Digitransit GraphQL endpoints:
- **HSL (Helsinki region)**: `https://api.digitransit.fi/routing/v2/hsl/gtfs/v1` (selected with `fi:hsl:<id>`)
- **National (rest of Finland)**: `https://api.digitransit.fi/routing/v2/finland/gtfs/v1` (selected with `fi:<feed>:<id>`)

### Known Feed IDs & Regional Reittiopas

| Town / Region | Digitransit Feed ID | Aliases | Reittiopas (Stop Lookup) | Example in `stoppesteder.txt` |
| :--- | :--- | :--- | :--- | :--- |
| Helsinki (HSL) | `HSL` | `hsl`, `hki` | [reittiopas.hsl.fi](https://reittiopas.hsl.fi/) | `Kamppi = "fi:hsl:1020455"` |
| Tampere | `tampere` | — | [reittiopas.nysse.fi](https://reittiopas.nysse.fi/) | `Keskustori = "fi:tampere:0805"` |
| Turku (Föli) | `FOLI` | `turku`, `foli` | [reittiopas.foli.fi](https://reittiopas.foli.fi/) | `Kristiinankatu = "fi:turku:148"` |
| Oulu | `OULU` | `oulu` | [reittiopas.osl.fi](https://reittiopas.osl.fi/) | `Kauppatori = "fi:oulu:..."` |
| Joensuu | `Joensuu` | `joensuu`, `jojo` | [joensuu.digitransit.fi](https://joensuu.digitransit.fi/) | `Joensuun pääkirjasto I = "fi:joensuu:23575"` |
| Kuopio | `Kuopio` | `kuopio`, `vilkku` | [kuopio.digitransit.fi](https://kuopio.digitransit.fi/) | `Kuopion lentoasema = "fi:kuopio:303023"` |

Any other Digitransit Finland feed ID can be used directly as `fi:<feedId>:<stopId>` without needing an alias. To add a new town or operator alias, add it to `DIGITRANSIT_FEED_ALIASES` in [adapters/digitransit.py](digitransit.py).

### Finding Stop IDs & Feed IDs

- **Stop IDs**: Open your town's Reittiopas (for other cities, search e.g. `"reittiopas <town>"` such as `"reittiopas oulu"`), click on a stop, and copy the stop ID from the end of the URL (after `%3A`, e.g. `.../FOLI%3A148` → `148`).
- **Feed IDs** *(optional)*: To list all available `feedId`s in Digitransit Finland:
  ```bash
  curl -s -X POST https://api.digitransit.fi/routing/v2/finland/gtfs/v1 \
    -H "Content-Type: application/json" \
    -H "digitransit-subscription-key: $DIGITRANSIT_SUBSCRIPTION_KEY" \
    -d '{"query": "{ feeds { feedId } }"}'
  ```

### Adding Stops to `stoppesteder.txt`

Prefix the `gtfsId` with `fi:` under any section in `stoppesteder.txt` (see [example-stop-places/finland.txt](example-stop-places/finland.txt) for a full set of Finnish examples):

```ini
[turku]
Kristiinankatu = "fi:FOLI:148"
# or using the town alias:
Kristiinankatu = "fi:turku:148"
```

## Sweden

Sweden uses **Trafiklab ResRobot v2.1** (`RESROBOT_SUBSCRIPTION_KEY` in `.env`), which aggregates all of Sweden (SL Stockholm, Västtrafik, Skånetrafiken, SJ/national rail, regional buses, and ferries) under 9-digit `74xxxxxxx` Rikshållplats IDs.

### Finding Stop IDs

Use the built-in search command:
```bash
avgangstider search --se "T-Centralen" --city stockholm
```

Add the result to `stoppesteder.txt` with the `se:` prefix:
```ini
[stockholm]
T-Centralen T-bana = "se:740020749"
```

*(Note: Regional operators like SL and Västtrafik also have their own separate APIs if operator-specific features such as per-platform IDs are ever needed.)*

## Germany

For Germany we use **Transitous (MOTIS v2)** (`https://api.transitous.org/api/v1`), which requires no API key — only a contact `User-Agent` in `.env` (`TRANSITOUS_USER_AGENT`, or it falls back to `MET_USER_AGENT` / `ENTUR_CLIENT_NAME`).

### Finding Stop IDs

Find a stop name on [transitous.org](https://transitous.org/), [bahn.de](https://www.bahn.de/), or Google Maps, then run:
```bash
avgangstider search --de "Berlin Hbf"
```
The name doesn't have to bee exact. For example
```bash
avgangstider search --de "Alexanderplatz"
```
will list several stops.


Add the result to `stoppesteder.txt` with the `de:` prefix:
```ini
[berlin]
S+U Hauptbahnhof/Washingtonplatz (Berlin) = "de:de-VBB_de:11000:900003205::4"
```
