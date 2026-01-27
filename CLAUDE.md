## Project North Star

Before writing or modifying any code in this project, read and internalize `bible.md` at the project root. It defines the engineering philosophy, quality standards, and behavioral expectations for all work in this codebase.

Every decision — naming, architecture, error handling, refactoring — must align with the principles documented there. When in doubt, re-read the bible.

## Architecture

The frontend is split into ES modules (no build tools required). Hash-based routing powers `#/dashboard`, `#/holdings`, `#/company/:ticker`, and `#/export`.

```
index.html                  <- Shell: HTML skeleton + CDN links
css/
  styles.css                <- Robinhood light-mode theme
js/
  app.js                    <- Router, state manager, init
  config.js                 <- API key (gitignored) -- copy config.example.js
  config.example.js         <- API key template
  views/
    dashboard.js            <- Summary cards + recent updates
    holdings.js             <- Filterable company table
    company.js              <- Drill-down company page
    data-sync.js            <- Export/Import view
  components/
    header.js               <- Top bar nav with tabs
    sparkline.js            <- ApexCharts sparkline wrapper
    area-chart.js           <- ApexCharts area chart wrapper
  services/
    api.js                  <- Artemis (primary) + CoinGecko (fallback)
    csv.js                  <- CSV parse/export/IDE copy
    data-store.js           <- Central state, data loading, merge
  utils/
    format.js               <- formatNum, formatCompact, isRecent, getSecUrl
    dedup.js                <- Fingerprint-based transaction dedup
scraper/
  csv_sync.py               <- CLI: python -m scraper.csv_sync <csv> <ticker> <token>
```

## Running Tests

```
python3 -m pytest tests/ -v
```

## Key Patterns

- **Immutable by default**: Python dataclasses are frozen, JS merges return new arrays
- **Fingerprint dedup**: Transactions use `date:asset:totalCost` fingerprints for idempotent imports
- **API fallback chain**: Artemis -> CoinGecko -> null (never silent failure)
- **Atomic writes**: Python uses tempfile + os.replace() for crash safety
- **Chart cleanup**: `.destroy()` called on route change to prevent ApexCharts memory leaks
