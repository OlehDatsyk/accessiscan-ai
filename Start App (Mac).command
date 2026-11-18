#!/usr/bin/env bash
# AccessiScan AI - macOS launcher (double-click in Finder, or run from Terminal).
# Checks prerequisites, installs dependencies on first run, starts PostgreSQL (Docker, optional),
# applies migrations and starts the API (with scan worker) and the web app.
# It never deletes files and never resets the database.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"

fail() { echo; echo "[ERROR] $*"; echo "Startup stopped. Nothing was deleted."; read -r -p "Press Enter to close..." _; exit 1; }

echo "=========================================="
echo "  AccessiScan AI - starting local servers"
echo "=========================================="

# 1. Python 3.12+
PY=""
for c in python3.13 python3.12 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)'; then PY="$c"; break; fi
done
[ -n "$PY" ] || fail "Python 3.12+ not found. Install it with 'brew install python@3.12' or from python.org."
echo "[OK] Python: $($PY --version)"

# 2. Node.js
command -v node >/dev/null 2>&1 || fail "Node.js not found. Install the LTS version with 'brew install node' or from nodejs.org."
echo "[OK] Node.js: $(node --version)"

# 3. Backend venv + dependencies
if [ ! -x backend/.venv/bin/python ]; then
  echo "[..] Creating backend/.venv"
  "$PY" -m venv backend/.venv || fail "Could not create the virtual environment."
fi
VPY="$ROOT/backend/.venv/bin/python"
if [ ! -f backend/.venv/.deps-ok ]; then
  echo "[..] Installing backend dependencies (first run can take a few minutes)"
  "$VPY" -m pip install --upgrade pip >/dev/null
  "$VPY" -m pip install -r backend/requirements.txt || fail "Backend dependency installation failed."
  echo ok > backend/.venv/.deps-ok
fi

# 4. Chromium for Playwright
echo "[..] Checking the Playwright Chromium browser"
"$VPY" -m playwright install chromium || fail "Could not install Chromium for Playwright."

# 5. Frontend dependencies
if [ ! -d frontend/node_modules ]; then
  echo "[..] Installing frontend dependencies"
  (cd frontend && npm install --no-audit --no-fund) || fail "npm install failed."
fi

# 6. Environment
if [ ! -f backend/.env ] && [ ! -f .env ]; then
  echo "[i] No .env file found - using development defaults (AI disabled). Copy .env.example to backend/.env to configure."
fi

# 7. Database
USE_SQLITE=1
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "[..] Starting PostgreSQL with Docker Compose"
  if docker compose up -d db >/dev/null 2>&1; then
    for _ in $(seq 1 30); do
      if docker compose exec -T db pg_isready -U accessiscan -d accessiscan >/dev/null 2>&1; then USE_SQLITE=0; break; fi
      sleep 2
    done
  fi
fi
if [ "$USE_SQLITE" = 1 ]; then
  echo "[i] Docker not available - using local SQLite (backend/accessiscan-dev.db)"
  export DATABASE_URL="sqlite:///./accessiscan-dev.db"
else
  echo "[OK] PostgreSQL running on 127.0.0.1:55432"
  export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://accessiscan:accessiscan_local_dev@127.0.0.1:55432/accessiscan}"
fi

# 8. Migrations (additive only)
(cd backend && "$VPY" -m alembic upgrade head) || fail "Database migration failed."

if [ "${ACCESSISCAN_DRY_RUN:-0}" = 1 ]; then echo "[OK] Dry run finished - servers not started."; exit 0; fi

# 9. Start servers
export CORS_ORIGINS="http://localhost:$WEB_PORT,http://127.0.0.1:$WEB_PORT"
export VITE_DEV_API_PROXY="http://127.0.0.1:$API_PORT"
(cd backend && "$VPY" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT") &
API_PID=$!
(cd frontend && npm run dev -- --port "$WEB_PORT" --strictPort) &
WEB_PID=$!
trap 'echo; echo "Stopping..."; kill $API_PID $WEB_PID 2>/dev/null || true' INT TERM EXIT

echo
echo "  Web app:  http://localhost:$WEB_PORT"
echo "  API:      http://127.0.0.1:$API_PORT"
echo "  API docs: http://127.0.0.1:$API_PORT/api/docs"
echo "  Press Ctrl+C in this window to stop. PostgreSQL keeps running (docker compose stop db)."
sleep 6
open "http://localhost:$WEB_PORT" 2>/dev/null || true
wait
