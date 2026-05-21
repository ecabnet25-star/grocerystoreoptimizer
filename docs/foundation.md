# Grocery Optimizer Foundation

## Vision

Build a practical grocery optimization tool that balances nutrition, budget, and shelf life.

Rollout starts with Montreal and scales to any user-selected location through pluggable location profiles.

## MVP Goals

- Load grocery item catalogs from JSON.
- Compute optimized baskets under a fixed budget with configurable strategy modes.
- Optionally enforce category coverage.
- Allow category exclusions and weighted utility tuning.
- Support location-aware pricing (Montreal first).
- Expose a CLI for fast local planning.
- Provide JSON/CSV report exports.
- Provide test coverage for optimizer, data loading, and report generation.

## Optimization Approach

The current engine supports two strategy modes:

1. `greedy`: rank-by-value selection for fast decisions.
2. `knapsack`: dynamic-programming selection to maximize utility under budget.

Utility combines nutrition and shelf-life benefits with a cost penalty:

$$
utility = (nutrition \times w_n) + (shelfLife \times w_s) - (cost \times w_c)
$$

Selection flow:

1. Filter out excluded categories.
2. Apply selected strategy while respecting budget and optional max-item limit.
3. Attempt to include missing required categories when budget allows.
4. Return summary metrics and optional report outputs.

This design prioritizes practical tradeoffs between speed and quality while staying dependency-free.

## Data Contract

Catalog JSON format:

- `name` (string)
- `category` (string)
- `price` (number)
- `nutrition_score` (number)
- `shelf_life_days` (integer)
- `quantity` (integer, optional, default 1)

Location profile JSON format (`config/locations/<location>.json`):

- `location_id` (string)
- `display_name` (string)
- `currency` (string)
- `price_multiplier` (number)
- `category_price_multipliers` (object mapping category to number)
- `supported_postal_prefixes` (string list)
- `stores` (string list)

## Platform Architecture

- Core engine: shared optimization package used by all clients.
- CLI app: local execution and report export workflows.
- API backend: REST endpoints for website and mobile app integration.
- Frontend/mobile clients: consume `/locations` and `/optimize`.

## Roadmap

- Add meal-plan-aware optimization constraints.
- Add duplicate-item quantity tuning.
- Add household profile presets for weight templates.
- Add geospatial store-level pricing by postal code.
- Build web UI and mobile client on top of the API backend.
