# UniBite Issue Workbook Resolution

Audit source: `C:\Users\Ethan\Downloads\unibite_issues.xlsx`

Audit completed: 2026-07-18

This document maps every workbook issue to the implemented behavior and its verification path. Price facts are intentionally date-scoped because flyers change; the snapshot workflow must continue refreshing them.

## Resolution Matrix

| ID | Resolution | Evidence |
| --- | --- | --- |
| Q001 | Replaced stale/global-lowest scraping with date-valid structured flyer results. Multi-buy offers are converted to an effective unit price. On the audit date, PA romaine is represented as `2/$4` and valid through 2026-07-20, rather than the stale `$2.99` example. | `live_pricing/flipp.py`, `scrape_free_prices.py`, `test_unit_pricing_and_flipp.py` |
| Q002 | Added exact retailer matching, provider diagnostics, actual per-chain coverage, refresh failure thresholds, and last-known-good snapshot protection. Nine Montreal chains had verified quotes in the audited snapshot. | `live_pricing/engine.py`, `live_pricing/providers.py`, `free-live-pricing.yml` |
| Q003 | The Chef now returns structured recipes with recipe name, plan ingredients, optional extras, cook time, and three concise steps. | `assistant.py`, `test_assistant.py`, Playwright Chef flow |
| Q004 | Expanded the catalog from 10 to 34 items, corrected shelf-life score domination, and made catalog/must-have failure states explicit instead of silently repeating a narrow fallback basket. | `catalog.json`, `optimizer.py`, API optimizer tests |
| Q005 | Added the correct PA du Fort seed at 1420 Rue du Fort with verified coordinates. Nearby-store discovery and road routing use the resolved user origin. | `stores/montreal.json`, `/area/scan`, `/route/road` tests |
| Q006 | Added account food preferences stored in the production database and automatically merged into authenticated optimization requests. | database schema v4, `/users/{id}/profile`, profile API and Playwright tests |
| Q007 | Removed generic congratulations. Savings are shown only when the backend marks the calculation verified; otherwise the UI reports nutrition score and labels store totals as estimates. | `service.py`, `plan.js`, frontend tests |
| Q008 | Snapshot rows require schema v2, current fetch time, current offer validity, exact chain, product identity, source URL, and approved source type. The UI includes package/source context and deal expiry. | `providers.py`, `flipp.py`, `deals.py` |
| Q009 | The hero allocation is explicitly labeled as a sample and the non-food Savings segment was replaced with Dairy/alternatives. | `web/index.html`, `web/plan.js` |
| Q010 | Must-haves accept semicolon-separated names with optional package text, use normalized/fuzzy catalog matching, and return both matches and visible unmatched warnings. | `service.py`, `optimizer.py`, `plan.js` |
| Q011 | The planner exposes one location input for either postal code or address. The backend classifies the input and preserves origin type/display name; nearby scans explain when a centroid or approximate address is used. | `schemas.py`, `service.py`, `web/index.html` |
| Q012 | Every plan item can expose its top three store options with line total, package, normalized unit price, source status, and estimated savings. | `service.py`, `plan.js` |
| Q013 | Plan generation and post-generation refresh preserve the same complete request and origin. The same map instance is rebuilt with the returned route and all nearby locations. | `plan.js`, full Playwright integration |
| Q014 | Retailer coverage is calculated from actual nearby and priced stores using `verified_current`, `estimate_only`, and `nearby_only`; no unsupported chain is presented as live. | `service.py`, `plan.js`, `/deals` coverage |
| Q015 | Route selection is per-item and economics-aware. Extra stops must beat travel cost and minimum net-savings thresholds; the UI reports savings and added minutes only when verified. | route economics in `service.py`, route tests, Playwright map flow |
| Q016 | Added English/French switching across navigation, planner, generated insights, forecast, route, coverage, account, saved plans, About, and Chef output. | `shared.js`, `plan.js`, `price_prediction.py`, `assistant.py` |
| Q017 | Catalog and live quotes preserve package size and normalized price per 100 g, 100 ml, or unit. Location price adjustment now preserves package metadata. | `unit_pricing.py`, `models.py`, `location.py`, unit-pricing/location tests |
| Q018 | Added a deal-first Weekly Deals view before or after plan generation with category/store filters, savings/price/unit-price/expiry sorting, and one-click addition to must-haves. | `/deals`, `deals.py`, `plan.js`, deals and Playwright tests |

## Release Verification

- Python lint: `python -m ruff check src scripts tests`
- JavaScript syntax: `node --check web/plan.js`, `web/shared.js`, and `web/account.js`
- Unit/API suite: `python -m pytest -q`
- Browser integration: `python scripts/playwright_integration.py`
- Snapshot contract: `python scripts/scrape_free_prices.py --validate-only`
- Responsive visual checks: 390x844 and 1366x920, including generated plan, Account, Saved Plans, About, map tiles, route line, and page overflow
- Deployment bundle parity: enforced by `tests/test_frontend_theme.py`

## Ongoing Operational Requirement

Current pricing is not a one-time code fix. Keep the six-hour snapshot workflow healthy and monitor quote count, chain coverage, query failure rate, generated time, offer validity, and provider failure metrics. If the workflow rejects a refresh, investigate the upstream response before changing validation thresholds; the application should retain the last known-good snapshot rather than publish uncertain prices.
