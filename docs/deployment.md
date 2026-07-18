# Deployment Notes

## Environment Variables

- `GROCERY_DB_PATH`: SQLite file path for local/dev or a single-instance pilot.
- `GROCERY_DATABASE_URL`: PostgreSQL URL for production storage.
- `GROCERY_BACKUP_DIR`: Local SQLite backup directory used by `POST /maintenance/backup-database`.
- `GROCERY_MANAGED_BACKUPS_ENABLED`: Set `true` only after managed PostgreSQL PITR/backups are enabled.
- `GROCERY_API_CORS_ORIGINS`: Comma-separated allowed origins. Use explicit domains in production.
- `GROCERY_PUBLIC_BASE_URL`: Public HTTPS URL used by production readiness checks.
- `GROCERY_TOKEN_TTL_MINUTES`: Token expiry window in minutes.
- `GROCERY_ADMIN_TOKEN`: Required bearer token for maintenance, metrics, provider reload, and deployment status in production.
- `GROCERY_ROUTE_COST_PER_KM`: Route economics travel-cost estimate.
- `GROCERY_ROUTE_MIN_NET_SAVINGS`: Minimum net savings required before adding extra route stops.
- `GROCERY_ASSISTANT_MODE`: `hybrid`, `ollama`, or `fallback`.
- `GROCERY_ASSISTANT_OLLAMA_URL`: Ollama base URL (default `http://127.0.0.1:11434`).
- `GROCERY_ASSISTANT_OLLAMA_MODEL`: Free local model name (default `llama3.2:3b`).
- `GROCERY_ASSISTANT_OLLAMA_TIMEOUT_SECONDS`: Request timeout for model calls.
- `LIVE_PRICING_FLIPP_KEY`: Optional future licensed Flipp partner key; not required by the default public-flyer snapshot.
- `LIVE_PRICING_RETAILER_CATALOG_KEY`: Optional future licensed catalog key; not required by the default pipeline.

## Local API Run

```sh
python -m uvicorn grocery_optimizer.api.app:app --host 127.0.0.1 --port 8000 --app-dir src

```

## Local Health Checks

```sh
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/deployment/status
curl http://127.0.0.1:8000/observability/metrics

```

## Docker API Build and Run

```sh
docker build -f Dockerfile.api -t grocery-optimizer-api .
docker run --rm -p 8000:8000 grocery-optimizer-api

```

## Docker Compose (API + Web)

```sh
docker compose up --build

```

## Beta Smoke Automation

```powershell
powershell -ExecutionPolicy Bypass -File scripts/beta-smoke.ps1

```

## Production Suggestions

- Use managed PostgreSQL through `GROCERY_DATABASE_URL` for multi-instance or real production traffic.
- Enable managed PostgreSQL point-in-time recovery and set `GROCERY_MANAGED_BACKUPS_ENABLED=true`.
- Put API behind an HTTPS reverse proxy/load balancer and set `GROCERY_PUBLIC_BASE_URL=https://...`.
- Restrict `GROCERY_API_CORS_ORIGINS` to production frontend domains.
- Set a long random `GROCERY_ADMIN_TOKEN`; maintenance endpoints are blocked in production without it.
- Tune token TTL and schedule cleanup for old revoked tokens.
- Keep optional partner templates disabled unless licensed credentials are available. The default verified public-flyer snapshot requires no pricing key.

Maintenance endpoints available:

- `POST /maintenance/cleanup-tokens`
- `POST /maintenance/backup-database`
- `POST /pricing/providers/reload`

Operational endpoints:

- `GET /observability/metrics`
- `GET /deployment/status`
