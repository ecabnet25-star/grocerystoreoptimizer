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

## Current Pricing and Deals

The default production path does not require paid pricing keys. It uses structured public
Flipp flyer results to build `config/live_pricing/snapshots/latest.json`, then serves only
schema-v2 rows that pass retailer, product-identity, recency, and offer-validity checks.

- `verified_current`: a current, traceable flyer or ecommerce quote.
- `market_estimate`: a non-retailer estimate, never presented as verified savings.
- `tier_estimate_fallback`: a local store-tier estimate used when no verified quote matches.

The optimizer returns a fast estimate first. The browser then refreshes the exact same
request with current prices without blocking the initial plan. Verified savings are shown
only when all item assignments used for the savings calculation are verified.

Useful endpoints:

```text
GET /deals?postal_code=H3A1A1&sort=savings
GET /pricing/providers
GET /pricing/history?postal_code=H3A1A1&limit=200
POST /optimize
```

Refresh and validate the free snapshot locally:

```powershell
python scripts/scrape_free_prices.py
python scripts/scrape_free_prices.py --validate-only
```

The refresh script refuses to overwrite the last known-good snapshot when too many
queries fail, chain coverage collapses, the contract is invalid, or quote volume is too
low. `.github/workflows/free-live-pricing.yml` runs the same validation every six hours.
GitHub Actions must have repository read/write permission for that workflow to commit an
accepted snapshot.

`LIVE_PRICING_FLIPP_KEY`, retailer catalog keys, and OCR keys are optional future partner
integrations. Leave them blank unless a licensed provider has supplied credentials and its
disabled template has intentionally been enabled.

## The Chef

The Chef uses the generated shopping plan to return concise, structured recipes with a
name, plan ingredients, optional extras, cook time, and three steps. English and French are
supported. The built-in deterministic mode is the production default and has no model
dependency. Set `GROCERY_ASSISTANT_MODE=ollama` only when a local Ollama model is running;
`hybrid` keeps the fast deterministic behavior.

Assistant endpoints:

- `POST /assistant/chat`
- `GET /assistant/status`

## Store Discovery and Routing

Users enter one postal code or street address. The API resolves that origin, discovers
nearby grocery locations from public map data, retains all discovered locations for the map
and directory, and bounds pricing comparisons to the closest diverse candidates. The route
engine assigns items by store economics, removes stops that do not beat the configured
travel threshold, and the browser requests road-following geometry from OSRM. Straight-line
geometry appears only as an explicitly labeled fallback when road routing is unavailable.

Relevant endpoints:

- `GET /area/scan?postal_code=H3A1A1&radius_km=12`
- `POST /route/road`
- `POST /pricing/providers/reload` (admin protected in production)

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
