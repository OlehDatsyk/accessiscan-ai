# AccessiScan AI

**Real-browser web accessibility audits with transparent scoring and AI-assisted remediation.**

AccessiScan AI loads your pages in a real Chromium browser, runs the [axe-core](https://github.com/dequelabs/axe-core) accessibility engine against WCAG 2.2 Level A/AA rules, stores every result, and turns them into a prioritised, trackable remediation workflow — with optional AI explanations and code-fix suggestions from OpenAI, Anthropic or Google Gemini.

> **Automated testing cannot prove accessibility.** Tools like axe-core detect only part of WCAG 2.2. AccessiScan AI reports are automated assessments — not legal certification and not proof of conformance with WCAG, the ADA, the European Accessibility Act or EN 301 549. Every scan includes a manual-review checklist for the criteria a machine cannot judge.

## Live demo

| | URL |
|---|---|
| Web app | **https://accessiscan-ai-frontend.onrender.com** |
| API | https://accessiscan-ai-api.onrender.com |
| API docs | https://accessiscan-ai-api.onrender.com/api/docs |
| Health | https://accessiscan-ai-api.onrender.com/health/ready |
| Controlled test pages | https://accessiscan-ai-frontend.onrender.com/demo/violations.html · https://accessiscan-ai-frontend.onrender.com/demo/accessible.html |

The demo runs on Render's free plan in **demo mode**: data is temporary and is deleted whenever the service restarts, redeploys or sleeps (after ~15 minutes without traffic; the first request afterwards takes about a minute). AI features are not configured on the demo. Register any account, add the controlled test page above as a website and run a scan.

![Scan results](docs/screenshots/scan-results.png)

---

## Contents
1. [Product overview](#product-overview)
2. [Main features](#main-features)
3. [Technology stack](#technology-stack)
4. [Architecture](#architecture)
5. [How the scanning engine works](#how-the-scanning-engine-works)
6. [Accessibility standards and limitations](#accessibility-standards-and-limitations)
7. [Security model](#security-model)
8. [Screenshots](#screenshots)
9. [Installation](#installation)
10. [Local development](#local-development)
11. [Environment variables](#environment-variables)
12. [AI provider setup](#ai-provider-setup)
13. [Running tests](#running-tests)
14. [Deployment](#deployment)
15. [API documentation](#api-documentation)
16. [Project structure](#project-structure)
17. [Known limitations](#known-limitations)
18. [Licence](#licence)

---

## Product overview

AccessiScan AI is for website owners, developers, designers and agencies who need to find, understand and fix accessibility problems — and prove progress over time. Each website you add keeps its own scan history, analytics, monitoring schedule and issue backlog.

Results are always separated into four honest buckets:

| Bucket | Meaning |
|---|---|
| **Violations** | Rules axe-core confirmed as failing on specific elements |
| **Needs review** | Potential issues the engine could not confirm or rule out (axe "incomplete" results and AccessiScan heuristics) |
| **Manual review** | WCAG 2.2 criteria that require a human (keyboard traps, focus order, captions, meaningful alt text …) |
| **Passed checks** | Rules that ran and passed |

## Main features

- **Real scans** – Playwright + Chromium + axe-core 4.14; single page, list of URLs, or a limited same-site crawl (page/depth/time/size limits, robots.txt respected).
- **WCAG mapping you can trust** – success criteria come only from axe-core's own rule tags (e.g. `wcag143` → 1.4.3). Rules without a WCAG tag are labelled *best practice*; no mapping is invented.
- **Transparent score (0–100)** – documented formula, per-page deduction table, and an explicit "not a compliance rating" disclaimer.
- **Issue management** – filter by severity, type, category, WCAG criterion and status; full-text search; mark *in progress / fixed / ignored (with reason)*; notes; status history; bulk actions.
- **Honest fix tracking** – "marked fixed" is a manual claim; an issue only counts as *resolved* when a later scan no longer detects it. Fixed-but-still-detected issues are flagged as regressions; ignored decisions carry over to the next scan.
- **Scan comparison** – new, resolved and remaining issues, severity changes, score/passed-check/needs-review deltas, with a note on matching imperfections.
- **AI assistant (optional)** – explanations, user impact, before/after code suggestions, verification steps, audit summaries and fix priorities. Works only on detected issues; output is validated and labelled as a suggestion.
- **Built-in guidance** – hand-written, non-AI remediation guidance for common rules, available without any API key.
- **Contrast checker** – HEX/RGB input, live preview, AA/AAA for normal and large text, non-text contrast, nearest passing colour.
- **Reports** – PDF, CSV (formula-injection safe) and DOCX with methodology, WCAG mapping, remediation, manual checklist and limitations.
- **Monitoring** – opt-in daily/weekly/monthly scheduled scans with completion and regression notifications.
- **Dashboard & analytics** – all numbers computed from stored records: severity, categories, score trends, new vs resolved, score ranges, scan activity.
- **An accessible product** – the UI itself is tested with axe-core on every page (desktop and mobile), keyboard-navigable, with visible focus, skip link, labelled forms, accessible dialogs and tabs, data-table alternatives for charts and reduced-motion support.

## Technology stack

| Layer | Technologies |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL (SQLite for tests/dev fallback), PyJWT, Argon2id |
| Scanner | Playwright 1.65 (Chromium), axe-core 4.14, BeautifulSoup, custom SSRF-guarded egress proxy |
| Background jobs | Database-backed job queue + worker (embedded thread or separate process), scheduler |
| AI | Provider-independent layer over the OpenAI, Anthropic and Gemini HTTP APIs with Pydantic-validated JSON output |
| Reports | ReportLab (PDF), python-docx (DOCX), CSV |
| Frontend | React 19, TypeScript, Vite 7, Tailwind CSS 4, Radix UI Dialog, Lucide, Recharts, React Router 7, TanStack Query 5, React Hook Form, Zod |
| Testing | pytest (real browser scans against local fixture sites), Vitest + Testing Library, Playwright + @axe-core/playwright |
| Delivery | Docker (official Playwright image), Docker Compose, Render Blueprint, GitHub Actions |

## Architecture

```mermaid
flowchart LR
  U[Browser: React SPA] -- REST /api/v1 + JWT --> A[FastAPI API]
  A -- SQLAlchemy --> DB[(PostgreSQL)]
  A -- enqueue scan row --> DB
  W[Scan worker<br/>embedded thread or separate process] -- claim job (atomic UPDATE) --> DB
  W --> P[Guarded egress proxy<br/>127.0.0.1, per scan]
  W --> C[Headless Chromium<br/>fresh context per scan]
  C -- all traffic --> P -- public IPs only --> Internet((Public websites))
  A -- optional --> AI[OpenAI / Anthropic / Gemini]
```

- **API** – validates input, enforces ownership on every query, enqueues scans, serves results, reports and analytics.
- **Worker** – claims queued scans with a compare-and-set `UPDATE` (safe with several workers), runs the browser, commits each page in its own transaction, writes heartbeats, and finalises the scan in one transaction. Stale scans (worker crash/restart) are re-queued once, then failed — never left "running".
- **Scheduler** – inside the worker loop; creates scans for enabled monitoring configurations only.
- **Storage** – everything, including generated reports, lives in PostgreSQL (persistent, access-controlled). Browser temp files live in a per-scan temp directory that is deleted after the scan.

## How the scanning engine works

1. The URL is normalised and validated (scheme, credentials, port, host name, DNS → all addresses must be public).
2. A per-scan **guarded proxy** starts on `127.0.0.1`; Chromium is launched with `--proxy-server`, with the implicit loopback bypass removed and its own DNS resolution disabled, so *every* connection goes through the proxy.
3. A fresh incognito context is created (no downloads, service workers blocked, WebRTC disabled, media requests dropped).
4. The page is loaded (`load` + short `networkidle` wait). The final URL after redirects is validated again.
5. axe-core is injected with `page.evaluate` (not subject to the page's CSP) into the page and its frames, and run with the WCAG 2.0/2.1/2.2 A/AA (+ optional AAA) and best-practice tags.
6. Page metadata (title, language, headings outline, element counts) is extracted with BeautifulSoup, plus a labelled heuristic for generic link text (always "needs review").
7. For crawls, same-origin links are queued (fragments removed; logout/download links skipped; robots.txt honoured; depth/page limits; politeness delay).
8. Results are persisted per page; the scan is finalised with a summary, score, carry-over of ignored decisions, regression detection and notifications.

Limits (configurable, with hard caps in code): pages per scan (≤ 50), crawl depth (≤ 5), total scan time, per-page timeout, per-page and per-scan download budgets, redirects, allowed ports, per-user active scans, per-user hourly scans, worker concurrency.

### Scoring

```
page score = max(0, 100 − Σ weight(impact) × (1 + 0.1 × min(affected elements − 1, 10)))
scan score = mean(page scores of successfully scanned pages)
weights: critical 10 · serious 6 · moderate 3 · minor 1
```
Needs-review items and manual checks do not affect the score. Every scan shows the per-rule deductions behind its score. The score is a relative indicator of automatically detected problems, **not** a WCAG conformance rating — a score of 100 does not mean a page is accessible.

## Accessibility standards and limitations

- Rules: axe-core's WCAG 2.0, 2.1 and 2.2 Level A/AA rules plus best practices; optional AAA rules (e.g. enhanced contrast).
- WCAG 2.2 success criteria are shown with their level; 4.1.1 Parsing is labelled obsolete.
- Automated testing typically finds a minority of real-world barriers. Not covered automatically: meaningful alt text quality, logical focus order, keyboard traps, captions and audio description, error handling flows, content on hover/focus, cognitive accessibility, and most interaction behaviour. The manual-review checklist lists these with test instructions.
- Pages are tested anonymously at a 1280 × 900 desktop viewport. Content behind logins, paywalls, CAPTCHAs or interactions is not tested, and the scanner never tries to bypass them.

## Security model

The scanner fetches user-supplied URLs, so it is designed as an SSRF-hardened component:

- **URL validation**: http/https only; no credentials; ports allow-list; `localhost`, `*.local`, `*.internal`, metadata host names refused; legacy IPv4 notations (`127.1`, `2130706433`, `0x7f.1`) decoded the way browsers do; DNS resolved and *all* addresses must be public (loopback, RFC 1918, link-local incl. `169.254.169.254`, CGNAT, ULA, multicast, reserved, IPv4-mapped / NAT64 / 6to4 / Teredo forms rejected).
- **Network-level enforcement**: every browser connection — redirects, sub-resources, fetch/XHR, WebSockets, iframes — passes the guarded proxy, which re-validates, **pins the validated IP** (defeats DNS rebinding), enforces download budgets and idle timeouts. Tests prove a local "internal service" receives zero requests in redirect, sub-resource, iframe, WebSocket and metadata scenarios.
- **Isolation**: separate browser process and incognito context per scan, downloads disabled, temp dirs removed, internal URLs/credentials never sent to scanned sites.
- **Abuse limits**: per-user active/hourly scan limits, worker concurrency, page/time/size limits, polite crawling.
- **Accounts**: Argon2id hashing, short-lived HS256 JWTs with audience/issuer/version claims, rotating refresh tokens with reuse detection, login throttling, token revocation on password change / "sign out everywhere".
- **Data isolation**: every query filters by owner; foreign IDs return 404. Tested across all endpoints.
- **AI safety**: scanned content treated as untrusted data in a delimited block; outputs schema-validated; WCAG references and issue IDs filtered to real data; per-user daily limits; keys only in server environment variables.

Full details, threat model and residual risks: [SECURITY.md](SECURITY.md).

## Screenshots

All screenshots are genuine captures of the application scanning the local fixture site in `backend/tests/fixtures_site` (generated by `frontend/e2e/screenshots.spec.ts`).

| Dashboard | Issue detail |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Issue detail](docs/screenshots/issue-detail.png) |
| **Issues** | **Scan comparison** |
| ![Issues](docs/screenshots/issues.png) | ![Compare](docs/screenshots/compare.png) |
| **Contrast checker** | **Crawl: scanned pages** |
| ![Contrast checker](docs/screenshots/contrast-checker.png) | ![Crawl pages](docs/screenshots/crawl-pages.png) |

## Installation

Prerequisites: **Python 3.12+**, **Node.js 20.19+ (22 LTS recommended)**, optionally **Docker Desktop** (for PostgreSQL).

```bash
git clone https://github.com/OlehDatsyk/accessiscan-ai.git
cd accessiscan-ai
```

**Windows:** double-click **`Start App.bat`**.
**macOS:** double-click **`Start App (Mac).command`** (first time: right-click → Open, or `chmod +x "Start App (Mac).command"`).

The launchers check prerequisites, create the virtual environment, install backend/frontend dependencies and Chromium, start PostgreSQL with Docker Compose (or fall back to SQLite when Docker is not running), apply migrations and start the app at **http://localhost:5173** (API on http://127.0.0.1:8000). They never delete files or reset the database.

## Local development

```bash
# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m playwright install chromium                  # Linux: add --with-deps
docker compose up -d db                                # from the repo root; or set DATABASE_URL=sqlite:///./dev.db
alembic upgrade head
uvicorn app.main:app --reload --port 8000              # starts the embedded scan worker too

# Frontend (second terminal)
cd frontend
npm install
npm run dev                                            # http://localhost:5173, proxies /api to :8000
```

Run the worker as a separate process instead: set `RUN_EMBEDDED_WORKER=false` for the API and run `python -m app.worker`.

Full stack in containers (PostgreSQL, API, dedicated worker, nginx frontend): `docker compose up --build` → http://localhost:8080.

To scan a local test site during development, allow-list it explicitly (refused in production): `SCANNER_ALLOW_HOSTS=127.0.0.1:8765`.

## Environment variables

See [`.env.example`](.env.example) for every variable with defaults. The most important:

| Variable | Required | Sensitive | Purpose |
|---|---|---|---|
| `ENVIRONMENT` | yes (prod) | no | `production` enables strict checks (secret length, no allow-list, no wildcard CORS) and HSTS |
| `SECRET_KEY` | yes | **yes** | JWT signing key (≥ 32 random characters in production) |
| `DATABASE_URL` | yes | **yes** | PostgreSQL URL (`postgres://` / `postgresql://` are normalised to psycopg 3) |
| `CORS_ORIGINS` | yes (prod) | no | Comma-separated frontend origins |
| `FRONTEND_URL` | no | no | Public frontend URL |
| `TRUSTED_PROXY_HEADERS` | no | no | Use `X-Forwarded-For` for client IPs (only behind a trusted proxy) |
| `RUN_EMBEDDED_WORKER` | no | no | Run the scan worker inside the API process (default `true`) |
| `EPHEMERAL_DEMO` | no | no | Demo without a persistent database: allows SQLite in production and shows a "data is temporary" banner |
| `AI_PROVIDER` / `AI_MODEL` | no | no | `none` (default), `openai`, `anthropic`, `gemini`; optional model override |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | no | **yes** | Key for the selected provider |
| `SCAN_*` | no | no | Scanner limits (pages, depth, timeouts, sizes, rate limits, ports) |
| `VITE_API_URL` | frontend build | no | API origin for a separately hosted frontend; empty = same origin |

## AI provider setup

AI is optional — the app starts and works without any key (AI buttons are disabled with an explanation; built-in guidance remains).

```env
AI_PROVIDER=anthropic          # or openai / gemini
ANTHROPIC_API_KEY=...          # set in the server environment only, never in the frontend
AI_MODEL=claude-sonnet-5-5     # optional; defaults: gpt-5-mini, claude-sonnet-5-5, gemini-2.5-flash
AI_DAILY_REQUEST_LIMIT=40      # per user, rolling 24 h
```

Safeguards: requests time out (`AI_TIMEOUT_SECONDS`), output tokens are capped (`AI_MAX_OUTPUT_TOKENS`), remediation suggestions are cached per issue, token usage is logged per request, and invalid output is rejected (HTTP 502) instead of being shown.

## Running tests

```bash
# Backend: unit, auth, API workflow, real-browser scanner, SSRF, AI (mocked) - 139 tests
cd backend && pytest -q
# against PostgreSQL as well:
TEST_DATABASE_URL=postgresql+psycopg://user:pass@127.0.0.1:55432/accessiscan_test pytest -q
ruff check . && ruff format --check app tests

# Frontend
cd frontend
npm run lint && npm run typecheck && npm test && npm run build
npx playwright test            # E2E + axe-core on every page (starts backend, fixture site and preview)
```

No test contacts an external website: scans run against `backend/tests/fixtures_site` (pages with known violations and a known-good page) and a local "internal service" used to prove SSRF protection. AI providers are mocked.

## Deployment

The repository contains a Render Blueprint ([`render.yaml`](render.yaml)):

| Service | Type | Notes |
|---|---|---|
| `accessiscan-ai-api` | Web service, **Docker** | FastAPI + embedded scan worker; image based on `mcr.microsoft.com/playwright/python:v1.65.0-noble` (Chromium + OS libraries included) |
| `accessiscan-ai-frontend` | Static site | React build, SPA rewrite, CSP headers |
| `accessiscan-ai-worker` | Background worker (commented) | For paid plans with PostgreSQL; set `RUN_EMBEDDED_WORKER=false` on the API |

The published Blueprint runs in **demo mode** (`EPHEMERAL_DEMO=true`): the API stores data in SQLite on the free instance's disk, which Render wipes on restart, redeploy and idle sleep, and the UI shows a permanent "data is temporary" banner. For persistent data, add a PostgreSQL database (instructions at the top of `render.yaml`) and remove `EPHEMERAL_DEMO`.

The frontend also publishes two controlled test pages – `/demo/violations.html` (known defects) and `/demo/accessible.html` (known-good) – so a deployment can be verified without scanning third-party sites.

The Docker runtime is required — Render's native Python runtime does not include Chromium's system libraries. Migrations run on container start (`alembic upgrade head`, additive only). Health check: `/health/ready`. See [INSTRUCTION.md](INSTRUCTION.md#deploying-to-render) for step-by-step deployment and plan sizing.

## API documentation

Interactive OpenAPI docs are served at **`/api/docs`** (ReDoc at `/api/redoc`, schema at `/api/openapi.json`) when `DOCS_ENABLED=true`. All endpoints are versioned under `/api/v1/`: `auth`, `users`, `websites`, `scans`, `issues`, `ai`, `reports`, `dashboard`, `analytics`, `monitoring`, `notifications`, `tools/contrast`, `wcag`, `scoring`.

## Project structure

```
accessiscan-ai/
├─ backend/
│  ├─ app/
│  │  ├─ api/            # routers: auth, websites, scans, issues, ai, reports, analytics/monitoring
│  │  ├─ scanner/        # engine.py (Playwright+axe), proxy.py (SSRF guard), url_safety.py, heuristics.py, vendor/axe.min.js
│  │  ├─ ai.py           # provider layer + prompts + output validation
│  │  ├─ worker.py       # DB job queue worker, stale-job recovery, scheduler
│  │  ├─ services.py     # persistence, summaries, comparison, carry-over, notifications
│  │  ├─ scoring.py, wcag.py, contrast.py, reports.py, guidance.py
│  │  └─ models.py, schemas.py, security.py, config.py, main.py
│  ├─ alembic/           # migrations
│  ├─ tests/             # pytest suites + fixtures_site (local test website)
│  └─ Dockerfile
├─ frontend/
│  ├─ src/               # pages, components (accessible UI kit, charts), api client, lib
│  ├─ e2e/               # Playwright + axe-core tests, screenshot capture
│  └─ Dockerfile, nginx.conf
├─ docs/screenshots/
├─ .github/workflows/ci.yml
├─ docker-compose.yml, render.yaml, .env.example
├─ Start App.bat, Start App (Mac).command
└─ README.md, INSTRUCTION.md, SECURITY.md, PROJECT_REVIEW.md, CHANGELOG.md, LICENSE
```

## Known limitations

- Automated results cover only part of WCAG; manual and assistive-technology testing remain essential.
- No authenticated scanning (login flows), no organisation/team accounts (resources are per user), no e-mail notifications (in-app only).
- Issue matching across scans uses rule + page + CSS selector and can be imperfect when markup changes.
- A scanned page's own JavaScript runs in the same world as axe-core and could tamper with its *own* results.
- On Render's free plan the API sleeps when idle, has 512 MB RAM and scans slowly; heavy pages or crawls may exceed memory. Free PostgreSQL expires after 30 days.
- The macOS launcher has not been run on real macOS hardware during development.

## Licence

[MIT](LICENSE) © 2026 Oleh Datsyk. axe-core is © Deque Systems, Inc. and distributed under the Mozilla Public License 2.0 (`backend/app/scanner/vendor/`).
