# New Features Added - Multi-Location and Store Finding

## Overview

This update adds comprehensive location-based features including postal code support, store finding, price comparison, and route optimization for US and Canada.

## Core Features

### 1. Multi-Location Support

- **Montreal, QC** (Canada)
- **Toronto, ON** (Canada)
- **New York, NY** (United States)
- **Los Angeles, CA** (United States)

Each location has:

- Custom pricing multipliers
- Category-specific price adjustments
- Supported postal code prefixes
- List of available grocery store chains
- Currency support (CAD/USD)

### 2. Store Database

Created comprehensive store data for all locations:

- 17 stores total across 4 cities
- Store details include:
  - Name, chain, and address
  - Latitude/longitude coordinates
  - Price tier (budget/mid/premium)
  - Quality rating (1.0-5.0)
  - Location association

**Store Chains by Location:**

- Montreal: IGA, Metro, Provigo, Super C, Maxi
- Toronto: Loblaws, Metro, No Frills, Wholesale Club
- New York: Whole Foods, Trader Joe's, Fairway, ALDI  
- Los Angeles: Whole Foods, Trader Joe's, Ralphs, Food 4 Less

### 3. Postal Code System

Added postal code lookup system with coordinates:

- 12 postal codes across 4 cities
- Geographic data (latitude/longitude)
- City, province/state, country information
- Supports both US (5-digit) and Canadian (letter+number) formats

### 4. Distance Calculation

Implemented Haversine formula for accurate distance calculation:

- Calculates distance in kilometers between any two coordinates
- Used for finding nearby stores
- Used for route optimization

### 5. Store Finding

New `find_nearby_stores()` function:

- Takes user postal code
- Returns stores within configurable radius (default 20km)
- Sorted by distance from user
- Includes all store details and distance

### 6. Price Comparison

Enhanced optimizer returns per-store pricing:

- Base prices adjusted by store price tier:
  - Budget stores: -15% (0.85x multiplier)
  - Mid-tier stores: standard (1.0x multiplier)
  - Premium stores: +25% (1.25x multiplier)
- Estimated total cost at each nearby store
- Value score calculation (quality/price ratio)

### 7. Route Optimization

Implemented nearest-neighbor route algorithm:

- Starts from user location (postal code)
- Visits stores in optimal order to minimize distance
- Returns:
  - Stop order
  - Distance between each stop
  - Total route distance

## API Changes

### New Endpoints

#### GET /locations

Enhanced to return detailed location data:

```json
{
  "locations": [
    {
      "location_id": "montreal",
      "display_name": "Montreal, QC",
      "currency": "CAD",
      "supported_postal_prefixes": ["H"],
      "store_chains": ["IGA", "Metro", "Provigo", "Super C", "Maxi"]
    }
  ]
}

```

#### GET /stores?postal_code=XXX&max_distance=20

Find stores near a postal code:

```json
{
  "postal_code": "H3A1A1",
  "max_distance_km": 20.0,
  "stores": [
    {
      "store_id": "iga-downtown-mtl",
      "name": "IGA Downtown",
      "chain": "IGA",
      "address": "1444 Rue Sainte-Catherine O, Montreal, QC",
      "distance_km": 0.98,
      "price_tier": "mid",
      "quality_rating": 4.0
    }
  ],
  "count": 5
}

```

#### GET /stores?location=montreal

Get all stores in a location.

#### GET /postal-codes?country=CA

List supported postal codes:

```json
{
  "postal_codes": [
    {
      "postal_code": "H3A1A1",
      "city": "Montreal",
      "province_state": "QC",
      "country": "CA",
      "latitude": 45.5017,
      "longitude": -73.5673
    }
  ],
  "countries": ["CA", "US"]
}

```

### Enhanced Endpoint

#### POST /optimize

Now accepts `postal_code` parameter and returns:

- **stores.nearby**: List of nearby stores with distances
- **stores.comparison**: Price comparison across stores including:
  - Estimated total at each store
  - Distance from user
  - Price tier and quality rating
  - Value score
- **stores.data_source**: Attribution for pricing data
- **route**: Optimized route information:
  - Origin postal code coordinates
  - Ordered list of stops
  - Distance between each stop
  - Total route distance

Example response additions:

```json
{
  "stores": {
    "nearby": [...],
    "comparison": [
      {
        "store_id": "iga-downtown-mtl",
        "name": "IGA Downtown",
        "distance_km": 0.98,
        "price_tier": "mid",
        "quality_rating": 4.0,
        "estimated_total": 39.85,
        "value_score": 0.4
      }
    ],
    "data_source": "Based on location pricing profile and store tier pricing"
  },
  "route": {
    "origin": {
      "postal_code": "H3A1A1",
      "latitude": 45.5017,
      "longitude": -73.5673
    },
    "stops": [
      {
        "order": 1,
        "store_id": "iga-downtown-mtl",
        "name": "IGA Downtown",
        "distance_from_previous_km": 0.98
      }
    ],
    "total_distance_km": 14.05
  }
}

```

## Frontend Updates

### Form Enhancements

- Added postal code input field to optimization form
- Dynamic location dropdown populated from API
- Displays location with city and province/state

### New Display Sections

#### Store Comparison Table

Shows all nearby stores with:

- Store name and chain
- Distance from user
- Price tier
- Quality rating
- Estimated total cost
- Value score
- Data source attribution

#### Optimized Route Display

Shows suggested shopping route:

- Origin postal code
- Ordered stops with distances
- Total route distance
- Visual styling with brand color highlights

### JavaScript Modules

Updated modules:

- `shared.js`: Added `loadStores()` and `loadPostalCodes()` API wrappers
- `plan.js`: 
  - Enhanced location loading with full details
  - Added postal code to optimization request
  - Added store comparison rendering
  - Added route visualization

## Configuration Files Added

### Locations

- `config/locations/toronto.json`
- `config/locations/new-york.json`
- `config/locations/los-angeles.json`

### Stores

- `config/stores/montreal.json` (5 stores)
- `config/stores/toronto.json` (4 stores)
- `config/stores/new-york.json` (4 stores)
- `config/stores/los-angeles.json` (4 stores)

### Postal Codes

- `config/postal_codes/canada-qc.json` (3 codes)
- `config/postal_codes/canada-on.json` (3 codes)
- `config/postal_codes/usa-ny.json` (3 codes)
- `config/postal_codes/usa-ca.json` (3 codes)

## New Python Module

### `src/grocery_optimizer/stores.py`

New module providing:

- `Store` dataclass
- `PostalCodeInfo` dataclass
- `calculate_distance_km()` - Haversine distance formula
- `load_stores()` - Load store database
- `load_postal_codes()` - Load postal code lookup
- `find_nearby_stores()` - Find stores near postal code
- `optimize_route()` - Nearest-neighbor route optimization
- `get_price_tier_multiplier()` - Store tier pricing

## Testing

### Manual Testing

- Tested store loading: 17 stores loaded successfully
- Tested postal code lookup: 12 postal codes loaded
- Tested distance calculation: Montreal postal code finds 5 nearby stores
- Tested New York: Finds 4 nearby stores
- Tested optimization with postal code:
  - Returns store comparison data
  - Returns optimized route
  - Calculates per-store totals correctly

### Automated Testing

- All 20 existing tests still passing
- No regressions introduced

## Performance Considerations

- Store and postal code data loaded once at module import
- Distance calculations use efficient Haversine formula (O(1))
- Route optimization uses nearest-neighbor (O(nÂ²)) - acceptable for small n
- All operations complete in milliseconds

## Future Enhancements

Potential improvements for future versions:

- More cities and stores (Vancouver, Chicago, Seattle, etc.)
- Real-time pricing API integration
- More sophisticated route optimization (e.g., 2-opt, genetic algorithm)
- Map visualization (Google Maps, Mapbox)
- Store hours and inventory availability
- Traffic-aware routing
- Multi-day trip planning
- Store preference learning

## Breaking Changes

None. All existing API endpoints and functionality remain unchanged. New features are additive only.

## Migration Guide

No migration needed. Simply:

1. Pull latest code
2. Restart API server
3. Refresh web frontend

Existing saved plans and user data are fully compatible.
