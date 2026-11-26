# Local development

## With Docker Compose

```bash
scripts/init-env.sh        # once; --force replaces .env and invalidates old keys
docker compose up --build
```

- UI: http://localhost:3000 (sign in with a key printed by `init-env.sh`)
- API and OpenAPI docs: http://localhost:8000/docs
- Ports are bound to 127.0.0.1 only.

The backend runs `alembic upgrade head` on start, seeds the simulated account and scans it.

## Without Docker

Needs Python 3.12, Node 22+ and a PostgreSQL you can reach.

```bash
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]" && cd ..
PGPORT=5432 scripts/dev-backend.sh          # reads .env, migrates, serves :8000
npm --prefix frontend install && npm --prefix frontend run dev   # :3000
```

## Tests

```bash
cd backend && .venv/bin/pytest -q                       # SQLite, offline
CLOUDGINI_TEST_DATABASE_URL="$TEST_DB_URL" .venv/bin/pytest -q   # a postgresql+psycopg URL for an empty test database
cd ../frontend && npm run typecheck && npm run build
```

The tests cover: production changes blocked (also after a relabel between approval and execution),
unapproved actions refused, failed verification never marking Verified (automated and manual paths),
simulated data labelled everywhere, missing metrics giving no savings figure, irreversible actions
needing typed confirmation, demo reset returning to the same state, roles, validation, rate limiting,
and the GCP adapter's mapping on recorded-style fixtures.

## Resetting the demo

Cloud Accounts → **Reset simulated demo** (admin role), or `POST /api/demo/reset`. This restores the
simulated estate, clears its recommendations and actions, switches the account back to read-only and
re-scans. The audit log is append-only and keeps everything, including the reset itself.

## Useful environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CLOUDGINI_DATABASE_URL` | SQLite file | SQLAlchemy URL |
| `CLOUDGINI_API_KEYS` | empty (everything refused) | `name:role:sha256` entries |
| `CLOUDGINI_GCP_PROJECTS` | empty | real projects to register (read-only) |
| `CLOUDGINI_GCP_BILLING_TABLE` | empty | BigQuery billing export table |
| `CLOUDGINI_RATE_LIMIT_PER_MINUTE` | 120 | per key or IP |
| `CLOUDGINI_SENSITIVE_RATE_LIMIT_PER_MINUTE` | 10 | scan, approve, execute, assistant |
| `CLOUDGINI_ASSISTANT_MODEL` | `claude-opus-5-5` | model when `ANTHROPIC_API_KEY` is set |
