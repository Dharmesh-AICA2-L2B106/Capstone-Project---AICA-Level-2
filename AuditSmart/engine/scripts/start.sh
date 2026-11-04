#!/bin/sh
# Container start (Render free plan has no pre-deploy command, so migrations run here).
# 1. With DATABASE_URL set (Render Postgres): bring the schema to the latest Alembic revision.
#    Re-running is harmless: Alembic skips revisions already applied.
# 2. Start the API on $PORT (Render sets it; 8000 locally). Outside ENVIRONMENT=production the
#    app seeds the shared default rules and watched sources at start-up (idempotent).
set -eu
if [ -n "${DATABASE_URL:-}" ]; then
  echo "start.sh: alembic upgrade head"
  alembic upgrade head
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
