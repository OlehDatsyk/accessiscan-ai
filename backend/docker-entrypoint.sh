#!/bin/sh
# Usage: docker-entrypoint.sh api|worker|migrate
set -e
case "${1:-api}" in
  api)
    # Migrations are additive and idempotent; they never drop or reset data.
    python3 -m alembic upgrade head
    exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*' --no-server-header
    ;;
  worker)
    exec python3 -m app.worker
    ;;
  migrate)
    exec python3 -m alembic upgrade head
    ;;
  *)
    exec "$@"
    ;;
esac
