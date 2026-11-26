#!/usr/bin/env bash
# Run the backend without Docker (uses .env from scripts/init-env.sh and a local PostgreSQL).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
export CLOUDGINI_DATABASE_URL="${CLOUDGINI_DATABASE_URL:-postgresql+psycopg://cloudgini:${POSTGRES_PASSWORD}@127.0.0.1:${PGPORT:-5432}/cloudgini}"
cd backend
.venv/bin/alembic upgrade head
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"
