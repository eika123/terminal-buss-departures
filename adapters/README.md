# Documentation for certain adapters



## Finland

Finland uses two separate Digitransit GraphQL endpoints:
- **HSL (Helsinki region)**: `https://api.digitransit.fi/routing/v2/hsl/gtfs/v1` (selected with `fi:hsl:<id>`)
- **National (rest of Finland)**: `https://api.digitransit.fi/routing/v2/finland/gtfs/v1` (selected with `fi:<feed>:<id>`)

### Known Feed IDs

| Town / Region | Digitransit Feed ID | Aliases | Example in `stoppesteder.txt` |
| :--- | :--- | :--- | :--- |
| Helsinki (HSL) | `HSL` | `hsl`, `hki` | `Kamppi = "fi:hsl:1020455"` |
| Tampere | `tampere` | — | `Keskustori = "fi:tampere:0805"` |
| Turku (Föli) | `FOLI` | `turku`, `foli` | `Kristiinankatu = "fi:turku:148"` |
| Oulu | `OULU` | `oulu` | `Kauppatori = "fi:oulu:..."` |
| Joensuu | `Joensuu` | `joensuu`, `jojo` | `Joensuun pääkirjasto I = "fi:joensuu:23575"` |
| Kuopio | `Kuopio` | `kuopio`, `vilkku` | `Kuopion lentoasema = "fi:kuopio:303023"` |

Any other Digitransit Finland feed ID can be used directly as `fi:<feedId>:<stopId>` without needing an alias.

### Finding Feed IDs and Stop IDs

You can query Digitransit's GraphQL API directly with `curl` (requires `DIGITRANSIT_SUBSCRIPTION_KEY` from `.env`):

1. **List all available feed IDs:**
   ```bash
   curl -s -X POST https://api.digitransit.fi/routing/v2/finland/gtfs/v1 \
     -H "Content-Type: application/json" \
     -H "digitransit-subscription-key: $DIGITRANSIT_SUBSCRIPTION_KEY" \
     -d '{"query": "{ feeds { feedId } }"}'
   ```

2. **Look up a stop by name to get its exact `gtfsId` (`<feedId>:<stopId>`):**
   ```bash
   curl -s -X POST https://api.digitransit.fi/routing/v2/finland/gtfs/v1 \
     -H "Content-Type: application/json" \
     -H "digitransit-subscription-key: $DIGITRANSIT_SUBSCRIPTION_KEY" \
     -d '{"query": "{ stops(name: \"Kristiinankatu\") { gtfsId name code } }"}'
   ```

### Adding Stops to `stoppesteder.txt`

Prefix the `gtfsId` with `fi:` under any section in `stoppesteder.txt`:

```ini
[turku]
Kristiinankatu = "fi:FOLI:148"
# or using the town alias:
Kristiinankatu = "fi:turku:148"
```

Finland uses two separate Digitransit GraphQL endpoints:
- **HSL (Helsinki region)**: `https://api.digitransit.fi/routing/v2/hsl/gtfs/v1` (selected with `fi:hsl:<id>`)
- **National (rest of Finland)**: `https://api.digitransit.fi/routing/v2/finland/gtfs/v1` (selected with `fi:<feed>:<id>`)

### Known Feed IDs

| Town / Region | Digitransit Feed ID | Aliases | Example in `stoppesteder.txt` |
| :--- | :--- | :--- | :--- |
| Helsinki (HSL) | `HSL` | `hsl`, `hki` | `Kamppi = "fi:hsl:1020455"` |
| Tampere | `tampere` | — | `Keskustori = "fi:tampere:0805"` |
| Turku (Föli) | `FOLI` | `turku`, `foli` | `Kristiinankatu = "fi:turku:148"` |
| Oulu | `OULU` | `oulu` | `Kauppatori = "fi:oulu:..."` |
| Joensuu | `Joensuu` | `joensuu`, `jojo` | `Joensuun pääkirjasto I = "fi:joensuu:23575"` |
| Kuopio | `Kuopio` | `kuopio`, `vilkku` | `Kuopion lentoasema = "fi:kuopio:303023"` |

Any other Digitransit Finland feed ID can be used directly as `fi:<feedId>:<stopId>` without needing an alias.

### Finding Feed IDs and Stop IDs

You can query Digitransit's GraphQL API directly with `curl` (requires `DIGITRANSIT_SUBSCRIPTION_KEY` from `.env`):

1. **List all available feed IDs:**
   ```bash
   curl -s -X POST https://api.digitransit.fi/routing/v2/finland/gtfs/v1 \
     -H "Content-Type: application/json" \
     -H "digitransit-subscription-key: $DIGITRANSIT_SUBSCRIPTION_KEY" \
     -d '{"query": "{ feeds { feedId } }"}'
   ```

2. **Look up a stop by name to get its exact `gtfsId` (`<feedId>:<stopId>`):**
   ```bash
   curl -s -X POST https://api.digitransit.fi/routing/v2/finland/gtfs/v1 \
     -H "Content-Type: application/json" \
     -H "digitransit-subscription-key: $DIGITRANSIT_SUBSCRIPTION_KEY" \
     -d '{"query": "{ stops(name: \"Kristiinankatu\") { gtfsId name code } }"}'
   ```

### Adding Stops to `stoppesteder.txt`

Prefix the `gtfsId` with `fi:` under any section in `stoppesteder.txt`:

```ini
[turku]
Kristiinankatu = "fi:FOLI:148"
# or using the town alias:
Kristiinankatu = "fi:turku:148"
```
