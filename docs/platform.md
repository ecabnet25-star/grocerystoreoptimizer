# Platform Expansion Plan

## Montreal-First Rollout

- Current launch location: Montreal (`location_id: montreal`).
- Pricing adjustments come from `config/locations/montreal.json`.
- CLI and API default to Montreal if no location is specified.

## Multi-Location Model

To add a new location, create a new file in `config/locations`:

1. Copy `montreal.json`.
2. Update `location_id`, `display_name`, and multipliers.
3. Add postal prefixes and store list.
4. Launch and confirm with `GET /locations` or `--list-locations`.

No code changes are needed for standard location additions.

## Website and Mobile Compatibility

The API is designed as the shared backend for all clients:

- Web app: browser client calling `/optimize` and `/locations`.
- Mobile app: React Native / Flutter app using the same endpoints.
- Future geolocation: map user coordinates to nearest location profile and store.

Persistence support now exists:

- `POST /users` creates user profiles.
- `POST /auth/login` issues new tokens for existing users.
- `POST /users/{user_id}/plans` saves optimization runs.
- `GET /users/{user_id}/plans` retrieves user history (supports pagination).
- `GET /users/{user_id}/plans/{plan_id}` retrieves one saved plan.
- `PATCH /users/{user_id}/plans/{plan_id}` renames a saved plan.
- `DELETE /users/{user_id}/plans/{plan_id}` removes a saved plan.

Pagination contract:

- Request query: `limit`, `offset`
- Response metadata: `pagination.limit`, `pagination.offset`, `pagination.total`

Token model:

- Tokens are generated server-side and stored hashed in the configured database (PostgreSQL in production, SQLite in local development).
- Save/list plan endpoints require a valid user token.

## Suggested Production Architecture

- Backend API: FastAPI service (this repo).
- Frontend Web: React/Vue/Svelte app consuming API.
- Mobile App: React Native/Flutter consuming API.
- Data layer: database for user profiles, saved plans, and region-level pricing.

## Immediate Next Steps

- Add authentication for saved user plans.
- Add per-store pricing ingestion and postal-code routing.
- Deploy API and web client to cloud hosting.
