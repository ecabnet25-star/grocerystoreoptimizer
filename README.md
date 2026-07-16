# Grocery Optimizer

Student-friendly grocery planning tool with multi-location support, postal code-based store finding, and optimized shopping routes.

## Key Features

- **Multi-location support**: Montreal, Toronto, New York, Los Angeles (US & Canada)
- **Postal code-based store finding**: Enter your postal code to see nearby grocery stores
- **Store comparison**: Compare prices, quality ratings, and value across different stores
- **Route optimization**: Get an optimized route to visit multiple stores efficiently
- **Distance tracking**: See how far each store is from your location in kilometers
- **Smart optimization**: Greedy and knapsack algorithms with weighted utility scoring
- **Budget management**: Stay within budget while maximizing nutrition and freshness
- **Category control**: Require or exclude specific food categories
- **Shelf-life metrics**: Track average, shortest, and longest freshness
- **Multi-format reports**: Export plans as JSON or CSV
- **User accounts**: Save and manage favorite grocery plans
- **REST API**: Full HTTP API backend for web and mobile apps
- **Web interface**: Simple, student-friendly multi-page web UI

## Project Structure

- `src/` - Source code
  - `grocery_optimizer/stores.py` - Store finding, distance calculation, route optimization
  - `grocery_optimizer/location.py` - Location-based pricing profiles
- `docs/` - Documentation
- `tests/` - Test suite
- `config/` - Configuration files
  - `config/locations/` - Location pricing profiles (montreal.json, toronto.json, new-york.json, los-angeles.json)
  - `config/stores/` - Store data with addresses and coordinates
  - `config/postal_codes/` - Postal code lookup data (Canada and US)

## Supported Locations

### Canada

- **Montreal, QC**: IGA, Metro, Provigo, Super C, Maxi
  - Postal codes: H3A 1A1, H2X 1Y5, H4B 2M9, and more
- **Toronto, ON**: Loblaws, Metro, No Frills, Wholesale Club
  - Postal codes: M5H 2N2, M4C 1B5, M6G 1B7, and more

### United States

- **New York, NY**: Whole Foods, Trader Joe's, Fairway, ALDI
  - Postal codes: 10001, 10003, 10014, and more
- **Los Angeles, CA**: Whole Foods, Trader Joe's, Ralphs, Food 4 Less
  - Postal codes: 90001, 90012, 90028, and more

### Store Price Tiers

- **Budget**: 15% lower prices (e.g., Super C, No Frills, ALDI, Food 4 Less)
- **Mid**: Standard pricing (e.g., IGA, Metro, Trader Joe's, Ralphs)
- **Premium**: 25% higher prices (e.g., Whole Foods)

Each location has its own base price multiplier and category-specific adjustments for produce, protein, dairy, grains, and pantry items.

## Setup

1. Create a Python virtual environment:

   ```sh
   python -m venv venv
   ```

2. Activate the environment:

  - Windows: `venv\Scripts\activate`
  - macOS/Linux: `source venv/bin/activate`

1. Install dependencies:

   ```sh
   pip install -r requirements.txt
   ```

For development and CI-equivalent local checks:

```powershell
python -m pip install -e ".[dev]"
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -SkipInstall
```

## Usage

Quick launch (recommended):

```sh
powershell -ExecutionPolicy Bypass -File launch.ps1

```

## Third-Party Live Pricing Setup

The project supports real third-party pricing sources through configurable providers.

### Pricing pipeline

UniBite/UniBite.click gets current prices from enabled live-pricing providers first, then falls back to store-tier estimates when a provider cannot return a quote.

Current provider types include:

- public benchmark feeds for generic live validation
- retailer/provider adapters configured in `config/live_pricing/providers.json`
- opt-in scraping adapters for feeds that are only exposed through flyer pages or retailer web endpoints

The live snapshot endpoint used by the web app is `GET /pricing/live`. The app also exposes `GET /pricing/providers` so you can verify which providers are enabled and returning quotes. For route planning and map discovery, the app can combine those live prices with public location data and local store catalogs as a fallback.

1. Edit `config/live_pricing/providers.json`.
2. Enable at least one provider: set `"enabled": true`.
3. If the provider requires API keys, set env vars before launch.

Example (PowerShell):

```powershell
$env:LIVE_PRICING_RAPIDAPI_KEY = "your-api-key"
$env:LIVE_PRICING_ALLOW_SCRAPING = "true"   # only if you intentionally enable html scraping provider

```

Check provider status:

```text
GET http://127.0.0.1:8000/pricing/providers

```

Live pricing snapshot endpoint:

```text
GET http://127.0.0.1:8000/pricing/live?location=montreal&postal_code=H3A1A1&budget=100&max_items=8&strategy=knapsack

```

Notes:

- If no provider returns quotes, the system automatically falls back to store-tier estimates.
- HTML scraping is opt-in and requires `LIVE_PRICING_ALLOW_SCRAPING=true`.
- Respect each retailer's terms of service and robots policy when enabling scraping.

## Free-Only Live Pricing (No Paid APIs)

The project now supports a free-only pipeline by default:

- Free retailer page scraping for Metro, IGA, Maxi, Provigo, and Super C
- Free Flipp public search-page scraping for flyer deal hints
- Free Open Food Facts quote coverage (`openfoodfacts_us_ca`)
- Free benchmark fallback (`public_market_benchmark`)

Scraper source config:

- `config/live_pricing/free_scrape_sources.json`

Snapshot output used by live providers:

- `config/live_pricing/snapshots/latest.json`

Run scraper locally:

```powershell
python scripts/scrape_free_prices.py --max-items 30
```

### GitHub Actions Auto-Refresh (Free Scheduler)

Workflow:

- `.github/workflows/free-live-pricing.yml`

It runs every 6 hours and commits snapshot updates back to the repo.

One-time step you need to do in GitHub:

1. Repository Settings -> Actions -> General
2. Set Workflow permissions to **Read and write permissions**

Without this setting, the workflow cannot push updated snapshot commits.

### Retailer-Specific Scraper Jobs (Metro, IGA, Maxi, Provigo)

Dedicated provider entries and scheduled jobs are now preconfigured:

- Providers: `metro_qc_html_scraper`, `iga_qc_html_scraper`, `maxi_qc_html_scraper`, `provigo_qc_html_scraper`
- Jobs file: `config/live_pricing/jobs.json`
- Job runner: `scripts/run_live_pricing_jobs.py`

Run all due jobs once:

```powershell
$env:LIVE_PRICING_ALLOW_SCRAPING = "true"
python scripts/run_live_pricing_jobs.py --once
```

Force-run all enabled jobs once (ignores schedule intervals):

```powershell
python scripts/run_live_pricing_jobs.py --once --force --reload-providers
```

Register recurring Windows Task Scheduler job:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_live_pricing_jobs.ps1 -IntervalMinutes 30
```

Remove scheduled task:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_live_pricing_jobs.ps1 -Remove
```

### No-Paid-API Mode

For strict free-only operation, keep paid/managed providers disabled in `config/live_pricing/providers.json`.
The default configuration already keeps those entries disabled.

### Historical Median Sanity Filtering

Transient spikes are filtered using historical medians per item + store chain + postal code.

Config knobs in `config/live_pricing/providers.json`:

- `history_min_samples`
- `history_min_confidence`
- `history_max_rows`
- `history_max_deviation_ratio`

## Free Local AI Assistant (Ollama)

The meal assistant can run on a free local model using Ollama.

1. Install Ollama: https://ollama.com/download
2. Pull a model (recommended fast option):

```powershell
ollama pull llama3.2:3b

```

1. Set assistant env vars (PowerShell):

```powershell
$env:GROCERY_ASSISTANT_MODE = "hybrid"   # hybrid or ollama
$env:GROCERY_ASSISTANT_OLLAMA_MODEL = "llama3.2:3b"
$env:GROCERY_ASSISTANT_OLLAMA_URL = "http://127.0.0.1:11434"

```

1. Launch app as usual:

```powershell
powershell -ExecutionPolicy Bypass -File launch.ps1 -Mode Local

```

Assistant APIs:

- `POST /assistant/chat`
- `GET /assistant/status`

If Ollama is unavailable, the assistant automatically falls back to built-in rule-based suggestions.

## Autonomous Area Scan and Continuous Refresh

The API can now auto-scan a postal-code area and build store candidates without pre-registering stores one-by-one.

- `GET /area/scan?postal_code=H3A1A1&radius_km=12`
  - Uses public map geodata scanning when available.
  - Falls back to local store catalog by distance when scan provider is unavailable.
  - This scan is automatically invoked during optimize/live pricing requests when `postal_code` is provided.

- `GET /pricing/history?postal_code=H3A1A1&limit=200`
  - Returns historical quote records (live + fallback) for analysis.

- `GET /pricing/scheduler/status`
- `POST /pricing/scheduler/start`
- `POST /pricing/scheduler/stop`
  - Background scheduler to continuously refresh pricing snapshots from watchlist areas.

Default scheduler watchlist config:

- `config/live_pricing/watchlist.json`

Runtime reload for provider config updates:

- `POST /pricing/providers/reload`

## Public Data Source Strategy for Non-Scrapable Stores

To maximize automation and avoid scraping-only limitations, the system includes a default enabled provider:

- `public_market_benchmark` (enabled by default)
  - Uses public market signals and basket multipliers from:
    - `config/live_pricing/public_benchmarks.json`
    - World Bank food inflation indicator (`FP.CPI.TOTL.ZG`)
  - Produces automated non-scraping price estimates per item/store.
  - Works even when retailer pricing pages block scraping or APIs are unavailable.

You can layer additional providers on top (retailer APIs, approved partner feeds) for higher-confidence direct quotes.

## Concrete US/Canada Partner Adapters Included

The provider chain now includes concrete adapters in priority order:

1. `openfoodfacts_us_ca` (`openfoodfacts_partner`, enabled)
  - Direct partner adapter for US/Canada product price records from Open Food Facts ecosystem.
  - Works without private API keys.

1. `flipp_us_ca_partner` (`flipp_partner`, optional)
  - Concrete adapter for flyer/deal partner APIs (US/CA).
  - Requires `LIVE_PRICING_FLIPP_KEY` and partner host config.

1. `public_market_benchmark` (`public_market`, enabled)
  - Public macro-price source fallback using World Bank indicator + basket multipliers.

This chain runs automatically. If a higher-priority direct partner quote is unavailable,
the system continues down the chain and still returns optimized results.

Windows launch button:

```text
Double-click launch.bat

```

Open this first after launching:

```text
http://127.0.0.1:8080

```

Launch modes:

- `-Mode Auto` (default): uses Docker when available, otherwise local Python servers
- `-Mode Docker`: requires Docker Desktop running
- `-Mode Local`: starts local API + web servers without Docker

Examples:

```sh
powershell -ExecutionPolicy Bypass -File launch.ps1 -Mode Local
powershell -ExecutionPolicy Bypass -File launch.ps1 -Mode Docker -Build
powershell -ExecutionPolicy Bypass -File launch.ps1 -Stop

```

Safe local stop helpers:

```powershell
powershell -ExecutionPolicy Bypass -File launch.ps1 -Stop
powershell -ExecutionPolicy Bypass -File scripts/stop-local.ps1

```

Run with defaults:

```sh
python src/main.py

```

Run with custom inputs:

```sh
python src/main.py --budget 75 --max-items 8 --required-categories produce protein

```

Run with the advanced strategy and category exclusions:

```sh
python src/main.py --strategy knapsack --budget 60 --required-categories produce protein --excluded-categories dairy

```

Run Montreal-first location optimization:

```sh
python src/main.py --location montreal --postal-code H2X1Y4 --strategy knapsack --budget 55 --required-categories produce protein

```

List configured locations:

```sh
python src/main.py --list-locations

```

Generate export reports:

```sh
python src/main.py --out-json outputs/plan.json --out-csv outputs/plan.csv

```

Use a custom catalog file:

```sh
python src/main.py --catalog config/catalog.json

```

Run tests:

```sh
python -m unittest discover -s tests -v

```

## CLI Options

- `--strategy`: `greedy` or `knapsack`
- `--nutrition-weight`, `--shelf-life-weight`, `--cost-weight`: utility scoring controls
- `--required-categories`: categories to include when budget permits
- `--excluded-categories`: categories to always skip
- `--out-json`, `--out-csv`: write optimization reports
- `--location`: location profile id (defaults to `montreal`)
- `--postal-code`: optional postal code (stored for hyper-local future logic)
- `--list-locations`: prints configured location ids from `config/locations`

## Web and Mobile Backend

This project can be used by a website or phone app through the API layer.

Install API dependencies:

```sh
pip install -r requirements-web.txt

```

Run the API server:

```sh
python -m uvicorn grocery_optimizer.api.app:app --host 127.0.0.1 --port 8000 --app-dir src

```

Key endpoints:

- `GET /`
- `GET /health`
- `GET /ready`
- `GET /locations`
- `POST /optimize`
- `GET /sample-request`
- `POST /users`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `POST /auth/logout-all`
- `POST /users/{user_id}/plans`
- `GET /users/{user_id}/plans`
- `GET /users/{user_id}/plans?limit=20&offset=0`
- `GET /users/{user_id}/plans/{plan_id}`
- `PATCH /users/{user_id}/plans/{plan_id}`
- `DELETE /users/{user_id}/plans/{plan_id}`
- `POST /maintenance/cleanup-tokens`

## Website Prototype

A lightweight browser client is included in `web/`.

Run a static server:

```sh
python -m http.server 8080 --directory web

```

Then open:

```text
http://127.0.0.1:8080

```

Keep the API running on `http://127.0.0.1:8000`.

The web prototype can now:

- Create a user profile
- Login by email to mint a fresh auth token
- Refresh and revoke tokens
- Run optimization
- Enter postal code to find nearby stores
- View store comparison with prices and distances
- See optimized route for visiting multiple stores
- Save optimized plans
- Load saved plan history
- Delete saved plans
- Rename saved plans

## Mobile App Path

The current API contract is ready for a phone app.

- Use `GET /locations` to populate selectable regions with details (supported postal codes, store chains, currency).
- Use `GET /stores?postal_code=XXX` to find nearby stores within 20km.
- Use `GET /postal-codes?country=US` or `country=CA` to list supported postal codes.
- Use `POST /optimize` for plan generation.
  - Include `postal_code` in request to get store comparison and route data.
  - Response includes `insights` with budget usage, category spending, best-store estimate, and next actions.
- Use `POST /users` and `POST /auth/login` to issue auth tokens.
- Use `POST /auth/refresh` with `Authorization: Bearer <token>` to rotate tokens.
- Use `POST /auth/logout` and `POST /auth/logout-all` with `Authorization: Bearer <token>` to revoke tokens.
- Use `POST /users/{user_id}/plans` with `Authorization: Bearer <token>` to save plans.
- Use `GET /users/{user_id}/plans` with `Authorization: Bearer <token>` to read saved plans.
- Pagination constraints: `limit` must be 1-100, `offset` must be >= 0.
- Paginated response includes `pagination.total` for client-side paging UX.
- Optimize response summary includes shelf-life insights: `average_shelf_life_days`, `shortest_shelf_life_days`, `longest_shelf_life_days`, and `total_units`.

## Environment Configuration

Copy `.env.example` values into your deployment environment:

- `GROCERY_DB_PATH`
- `GROCERY_API_CORS_ORIGINS`
- `GROCERY_TOKEN_TTL_MINUTES`
- `GROCERY_API_VERSION`
- `GROCERY_ENV`
- `GROCERY_ADMIN_TOKEN`
- `GROCERY_RATE_LIMIT_ENABLED`

See `docs/deployment.md` for deployment details and Docker usage.

## Beta Launch Artifacts

- `docs/beta-launch.md`: launch checklist and runbook
- `CHANGELOG.md`: beta release notes
- `.github/workflows/ci.yml`: automated CI test pipeline
- `docker-compose.yml`: one-command local beta stack

## Contributing

Pull requests and suggestions are welcome.
