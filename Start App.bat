@echo off
setlocal EnableExtensions EnableDelayedExpansion
title AccessiScan AI - launcher
cd /d "%~dp0"

rem ---------------------------------------------------------------------------------------------
rem  AccessiScan AI - Windows launcher
rem  Checks prerequisites, installs dependencies (first run), starts PostgreSQL (Docker, optional),
rem  applies database migrations and starts the API (with scan worker) and the web app.
rem  It never deletes files and never resets the database.
rem ---------------------------------------------------------------------------------------------

if "%API_PORT%"=="" set "API_PORT=8000"
if "%WEB_PORT%"=="" set "WEB_PORT=5173"

echo.
echo  ==========================================
echo    AccessiScan AI - starting local servers
echo  ==========================================
echo.

rem --- 1. Python 3.12+ ---------------------------------------------------------------------------
set "PY="
where py >nul 2>nul && (py -3.12 -c "import sys" >nul 2>nul && set "PY=py -3.12")
if not defined PY (
  where python >nul 2>nul && (python -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>nul && set "PY=python")
)
if not defined PY (
  echo [ERROR] Python 3.12 or newer was not found. Install it from https://www.python.org/downloads/
  echo         and tick "Add python.exe to PATH" during installation.
  goto :fail
)
echo [OK] Python found: %PY%

rem --- 2. Node.js 20.19+ -------------------------------------------------------------------------
where node >nul 2>nul || (
  echo [ERROR] Node.js was not found. Install the LTS version from https://nodejs.org/
  goto :fail
)
for /f "delims=" %%v in ('node --version') do set "NODEV=%%v"
echo [OK] Node.js found: %NODEV%

rem --- 3. Backend virtual environment and dependencies --------------------------------------------
if not exist "backend\.venv\Scripts\python.exe" (
  echo [..] Creating Python virtual environment in backend\.venv
  %PY% -m venv backend\.venv || (echo [ERROR] Could not create the virtual environment. & goto :fail)
)
set "VPY=%~dp0backend\.venv\Scripts\python.exe"
if not exist "backend\.venv\.deps-ok" (
  echo [..] Installing backend dependencies - first run can take a few minutes
  "%VPY%" -m pip install --upgrade pip >nul
  "%VPY%" -m pip install -r backend\requirements.txt || (echo [ERROR] Backend dependency installation failed. & goto :fail)
  echo ok> "backend\.venv\.deps-ok"
) else (
  echo [OK] Backend dependencies installed. Delete backend\.venv\.deps-ok to reinstall.
)

rem --- 4. Chromium for Playwright (no-op when already installed) ---------------------------------
echo [..] Checking the Playwright Chromium browser
"%VPY%" -m playwright install chromium || (echo [ERROR] Could not install Chromium for Playwright. & goto :fail)
echo [OK] Chromium ready

rem --- 5. Frontend dependencies ---------------------------------------------------------------------
if not exist "frontend\node_modules" (
  echo [..] Installing frontend dependencies
  pushd frontend
  call npm install --no-audit --no-fund || (popd & echo [ERROR] npm install failed. & goto :fail)
  popd
) else (
  echo [OK] Frontend dependencies installed
)

rem --- 6. Environment configuration ---------------------------------------------------------------
if not exist "backend\.env" if not exist ".env" (
  echo [i] No .env file found - using safe development defaults. AI features stay disabled until you
  echo     copy .env.example to backend\.env and set AI_PROVIDER plus an API key.
)

rem --- 7. Database: PostgreSQL in Docker if available, otherwise local SQLite ------------------------
set "USE_SQLITE=1"
where docker >nul 2>nul && (
  docker info >nul 2>nul && (
    echo [..] Starting PostgreSQL with Docker Compose
    docker compose up -d db >nul 2>nul && set "USE_SQLITE=0"
  )
)
if "%USE_SQLITE%"=="1" goto :dbready
set /a TRIES=0
:waitdb
docker compose exec -T db pg_isready -U accessiscan -d accessiscan <nul >nul 2>nul && goto :dbready
set /a TRIES+=1
if !TRIES! GEQ 30 (
  echo [WARN] PostgreSQL did not become ready - falling back to SQLite.
  set "USE_SQLITE=1"
  goto :dbready
)
ping -n 3 127.0.0.1 >nul
goto :waitdb
:dbready
if "%USE_SQLITE%"=="1" (
  echo [i] Docker is not running - using a local SQLite database: backend\accessiscan-dev.db
  set "DATABASE_URL=sqlite:///./accessiscan-dev.db"
) else (
  echo [OK] PostgreSQL is running on 127.0.0.1:55432
  if not defined DATABASE_URL set "DATABASE_URL=postgresql+psycopg://accessiscan:accessiscan_local_dev@127.0.0.1:55432/accessiscan"
)

rem --- 8. Migrations (additive, never destructive) -----------------------------------------------
echo [..] Applying database migrations
pushd backend
"%VPY%" -m alembic upgrade head || (popd & echo [ERROR] Database migration failed. See the message above. & goto :fail)
popd
echo [OK] Database is up to date

if "%ACCESSISCAN_DRY_RUN%"=="1" (
  echo [OK] Dry run finished - all checks passed, servers not started.
  exit /b 0
)

rem --- 9. Start servers ------------------------------------------------------------------------------
set "CORS_ORIGINS=http://localhost:%WEB_PORT%,http://127.0.0.1:%WEB_PORT%"
set "VITE_DEV_API_PROXY=http://127.0.0.1:%API_PORT%"
start "AccessiScan API (port %API_PORT%)" cmd /k "cd /d "%~dp0backend" && "%VPY%" -m uvicorn app.main:app --host 127.0.0.1 --port %API_PORT%"
start "AccessiScan Web (port %WEB_PORT%)" cmd /k "cd /d "%~dp0frontend" && npm run dev -- --port %WEB_PORT% --strictPort"

echo.
echo  AccessiScan AI is starting in two new windows:
echo    Web app:   http://localhost:%WEB_PORT%
echo    API:       http://127.0.0.1:%API_PORT%
echo    API docs:  http://127.0.0.1:%API_PORT%/api/docs
echo    Health:    http://127.0.0.1:%API_PORT%/health/ready
echo.
echo  Close those windows to stop the servers. PostgreSQL keeps running in Docker
echo  (stop it with: docker compose stop db). Your data is kept.
echo.
ping -n 7 127.0.0.1 >nul
start "" "http://localhost:%WEB_PORT%"
pause
exit /b 0

:fail
echo.
echo  Startup stopped because of the error above. Nothing was deleted.
pause
exit /b 1
