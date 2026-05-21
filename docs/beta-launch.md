# Beta Launch Checklist

## Product Scope

- Montreal is the primary launch location.
- API supports user auth, optimization, and saved plan lifecycle (create/read/update/delete).
- Web prototype supports full API user flow.

## Pre-Launch Validation

- Run unit tests: `python -m unittest discover -s tests -v`
- Verify API health: `GET /health`
- Verify API readiness: `GET /ready`
- Verify CORS origins for beta domains.
- Confirm token TTL and cleanup policy.

## Operational Setup

- Configure env vars from `.env.example`.
- Persist database volume (`data/`) and schedule backups.
- Enable periodic token cleanup via `POST /maintenance/cleanup-tokens`.
- Track logs and monitor 4xx/5xx rates.

## Security Baseline

- Serve API behind HTTPS.
- Restrict CORS to trusted beta frontend origins.
- Rotate tokens periodically.
- Avoid committing production `.env` values.

## Launch Day Runbook

1. Deploy API and web frontend.
2. Validate `/health` and `/ready`.
3. Create test user via `/users`.
4. Run optimize, save plan, rename plan, and delete plan checks.
5. Monitor logs for first 60 minutes.

## Exit Criteria for Beta

- Error rate remains stable.
- Token/auth flows are reliable.
- Saved-plan lifecycle is stable under real usage.
- User feedback confirms Montreal pricing and flow quality.
