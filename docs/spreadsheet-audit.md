# Grocery Spreadsheet Audit

Source workbook: `C:\Users\Ethan\Downloads\grocery_2.xlsx`

Inspection date: 2026-06-26

> Historical research record. Current implementation status and pricing-source safeguards are documented in `unibite-workbook-resolution.md`. Since this audit, public map discovery, structured public flyer ingestion, verified quote labeling, and PA du Fort have been implemented; the deferred notes below describe the state at the original inspection date.

## Sheets Reviewed

1. `0. README & Method`
2. `Supermarkets (Full Table)`
3. `1. Retailers Master`
4. `2. Store Locations`
5. `3. Flyer Sources`
6. `4. Feasibility`
7. `5. Priority Ranking`
8. `6. Acquisition Strategy`

## Useful And Implemented

### Montreal Retailer Coverage

Useful because the project previously knew only a small Montreal chain set. The workbook identifies priority chains, source surfaces, and student relevance.

Implemented as:

- `config/retailer_research/montreal.json`
- `GET /retailer-research/montreal`
- `locations` response now includes compact retailer research.
- Optimization responses now include `stores.retailer_research`.
- Frontend plan results now show a Montreal retailer intelligence panel.

### Verified Store Seeds

Useful because the workbook includes a few coordinate-backed anchor stores that can improve routing immediately without fabricating full locator data.

Implemented as Montreal store seeds:

- T&T Ville St-Laurent
- Akhavan NDG
- PA du Parc

Deferred:

- Rows marked `PULL PROGRAMMATICALLY`.
- Rows with missing coordinates.
- H Mart as an MVP data source because the workbook marks it as weak for promo coverage.

### Priority Ranking

Useful because it gives an explicit scoring model for which retailers matter first.

Implemented as:

- Weighted priority data in `config/retailer_research/montreal.json`.
- The weighted scores were recalculated from workbook weights instead of relying on formula cache values.
- Tier 1 messaging in the frontend panel.

Highest-priority retailers:

1. Super C
2. Maxi
3. IGA / IGA Extra
4. Metro
5. Provigo
6. Walmart

### Acquisition Strategy

Useful because it separates MVP integrations from later ethnic/niche coverage and explains cadence.

Implemented as:

- Acquisition tiers in `config/retailer_research/montreal.json`.
- Disabled provider templates for:
  - Loblaw/PC Express partner or proxy
  - Metro e-commerce partner or proxy
  - IGA/Voila partner or proxy
  - Public flyer OCR pipeline
- Updated `.env.example` with matching API key environment variables.

## Useful But Deferred

### Full Store Locator Refresh

The workbook explicitly says full store locations should be pulled programmatically from official locators or Google Places. This is useful, but not complete from the workbook alone.

Deferred because:

- Exact counts are estimates.
- Several rows have no verified coordinates.
- A production Google Places key or official locator integration is needed.

### Flyer OCR Pipeline

Useful for ethnic-value retailers such as Supermarche PA and Akhavan.

Deferred because:

- It needs a separate OCR pipeline.
- It should run on public flyers with robots/terms review.
- It is valuable after Tier 1 pricing coverage is stable.

## Not Useful For Direct Implementation

### Unverified Counts

Not used for routing or exact claims. Counts remain research context only.

### ToS-Gray Scraping Routes

The workbook identifies undocumented Flipp/reebee and some internal retailer routes. These are not enabled directly.

Reason:

- Legal and stability risk.
- Production app should prefer official, partner, licensed, or controlled proxy feeds.

### Excluded MVP Sources

Not added as active pricing sources:

- Costco
- Dollarama
- H Mart
- public markets
- unverified Newon/Hawaii entries

Reason:

- Membership walls, weak promo surfaces, distorted unit comparisons, or unverified existence.

## New Feature Opportunities Identified

1. Retailer intelligence panel in plan results.
2. Store-source transparency for users and future admin UI.
3. Weekly Thursday flyer refresh job for Tier 1 retailers.
4. Monthly store-locator refresh using official locators or Google Places.
5. Ethnic-value flyer OCR after Tier 1 provider coverage is stable.
6. Admin dashboard for provider coverage by retailer/tier.

## Verification Targets

The integration is complete when:

1. `/retailer-research/montreal` returns the research payload.
2. `/locations` includes retailer research for Montreal.
3. `/optimize` includes `stores.retailer_research`.
4. Montreal store lookup includes the new coordinate-backed seed stores.
5. The frontend renders the retailer intelligence panel after plan generation.
6. Existing tests, browser smoke, and Playwright integration pass.
