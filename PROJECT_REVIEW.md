# AccessiScan AI – Project Review and Audit Report

**Date:** 18 November 2026 · **Version:** 1.0.0
**Scope:** backend, frontend, scanner engine, Playwright/axe-core integration, AI layer, database and migrations, authentication and authorisation, URL validation and SSRF defences, background jobs, reports, Docker, Docker Compose, Render Blueprint, launchers, CI, documentation and tests.

Every result below comes from commands that were actually executed on the development machine (Windows 11, Python 3.12.10, Node 24, Docker Desktop 29). Anything not executed is listed under *Not verified*.

## 1. Problems discovered

| # | Severity | Area | Problem |
|---|---|---|---|
| 1 | High | Scanner security | Legacy numeric IPv4 hosts (`127.1`, `0x7f.1`, `2130706433`) were not decoded before the IP check. Browsers interpret them as loopback; relying on the OS resolver was platform-dependent. |
| 2 | High | Frontend auth | After sign-in or registration the query cache was cleared in a way that detached the session observer, sending new users back to the sign-in page. |
| 3 | High | Accessibility | Dialogs controlled without a Radix trigger did not return keyboard focus to the opening control (focus fell to `<body>`). |
| 4 | Medium | Accessibility | While a lazily-loaded page was loading, the whole layout (incl. `<main>` and `<h1>`) was replaced by a spinner (`landmark-one-main`, `page-has-heading-one`). |
| 5 | Medium | Accessibility | Recharts SVGs contain focusable elements inside an `aria-hidden` wrapper (`aria-hidden-focus`). |
| 6 | Medium | Accessibility | Stat cards nested `<dt>` inside an extra `<div>` (`definition-list`, `dlitem`). |
| 7 | Medium | Accessibility | The marketing panel of the sign-in/registration pages was outside any landmark (`region`). |
| 8 | Medium | Accessibility | A scan in progress showed tab-panel `<h3>` headings directly after the `<h1>` (`heading-order`). |
| 9 | Medium | Performance | The issue list loaded every matching row and paginated in Python; report listings loaded every report's file bytes. |
| 10 | Low | Local dev | The default local PostgreSQL port (5433) collided with another service on the machine. |
| 11 | Low | Launcher | The Windows launcher used `goto` labels inside a parenthesised block and `timeout`, which fails without an interactive console. |
| 12 | Low | Docker | The worker container inherited the API's HTTP health check and would be reported unhealthy. |
| 13 | Low | Tooling | `@axe-core/playwright` pulled a second `playwright-core`, breaking E2E type checks and the production build (`tsc -b`). |
| 14 | Low | Code quality | Deprecated Starlette status constant; Ruff treated the local `alembic/` folder as first-party. |

No issue of critical severity remained open at any point of the audit.

## 2. Problems fixed

All 14 problems above were fixed:

1. WHATWG IPv4 parsing in `url_safety.legacy_ipv4()` – applied in validation and in the proxy; covered by new tests.
2. `AuthProvider` keeps the observed `me` query and replaces only other cached data (`endSession`), used by logout, session expiry, password change and account deletion.
3. `Dialog` remembers the focused element on open and restores it in `onCloseAutoFocus`; verified by E2E (`Escape` returns focus to *How is this calculated?*).
4. `Suspense` boundary moved inside `Layout` around `<Outlet/>`.
5. Chart wrappers are `aria-hidden` **and** `inert`; every chart has a data-table alternative.
6. `StatCard` uses `<div><dt/><dd/></div>` groups.
7. The panel is an `<aside aria-label="About AccessiScan AI">`.
8. The progress block has an `<h2>`.
9. SQL `COUNT` + `OFFSET/LIMIT` pagination with a portable JSON-text filter for WCAG criteria (validated pattern, no wildcards); `defer(Report.content)` for listings.
10. PostgreSQL published on `127.0.0.1:55432`.
11. Loop moved outside parentheses, `ping` delay, `<nul` stdin, `ACCESSISCAN_DRY_RUN=1` mode for verification.
12. Worker health check checks the main process instead.
13. npm `overrides` pin `playwright-core` to 1.65.0.
14. Literal `422`, Ruff isort configuration.

## 3. Security tests performed

Automated (all passing, `backend/tests/test_units.py`, `test_scanner.py`, `test_auth.py`, `test_workflow.py`, `test_ai.py`):

- **URL validation (41 malicious cases):** non-HTTP schemes (`file`, `ftp`, `javascript`, `data`, `gopher`), `localhost` variants, `.local`/`.internal`/metadata host names, loopback/private/link-local/CGNAT/reserved IPv4, IPv6 loopback/ULA/link-local, IPv4-mapped, NAT64 and 6to4 encodings, multicast, credentials in URLs, `user@host` confusion, disallowed ports (22, 6379), private/mixed/IPv6-local DNS answers, NXDOMAIN, whitespace/CRLF injection, backslash tricks, empty and over-long URLs, legacy IPv4 notations.
- **Real-browser SSRF tests** against a local "internal service" that counts requests: direct target, HTTP redirect to the internal service, redirect to `file://`, `<img>`, `<iframe>`, `fetch()`, WebSocket and `169.254.169.254` requests from a scanned page → **0 requests reached the internal service** in every case; blocked hosts are recorded.
- **Proxy tests:** `CONNECT` to loopback, rebinding host (DNS → 127.0.0.1), private host, `[::1]`, disallowed port, credentials in authority; absolute-form `GET` to the metadata IP and `2130706433`; non-HTTP and relative targets → all refused (403/400). IP pinning test: a host whose second DNS answer differs is never re-resolved.
- **Resource limits:** per-page download limit, per-scan download budget stopping the scan, page limit and depth limit for crawls, logout/PDF/external links not followed, robots.txt honoured, 404 pages reported as failed.
- **Production guards:** short secret, allow-list and wildcard CORS refused in production; allow-list ignored in production even if set.
- **Authentication:** Argon2id hash format, identical errors for unknown user / wrong password, login throttling (429), forged/expired/wrong-audience/wrong-type/revoked-version/`alg=none` JWTs rejected, refresh rotation and reuse detection (family revocation), logout revocation, password change invalidating access and refresh tokens, account deletion.
- **Authorisation / IDOR:** a second user received **404** for 18 cross-user operations (read/update/delete websites, analytics, monitoring, scans, pages, cancel, delete, issues, status, notes, reports create/download/delete, scan creation on a foreign website, AI remediation); bulk updates of foreign IDs change nothing; cross-user scan comparison refused.
- **API hardening:** CORS only for configured origins, security headers, 1 MB body limit (413).
- **AI:** disabled state (503 with configuration message), WCAG references and issue IDs filtered to real data, prompt-injection snippet cannot close the data block, invalid JSON / wrong schema rejected (502), daily limit (429), cross-user access (404, no provider call), API keys sent in headers not URLs, provider error mapping.
- **Reports:** CSV formula-injection neutralisation; disclaimer in CSV/PDF/DOCX.

Manual verification:
- Production Docker image: a scan inside the container under a **512 MB memory limit** completed (axe-core 4.14, Playwright 1.65) and blocked a request to `127.0.0.1:8000` made by the scanned page.
- Docker Compose stack (PostgreSQL + API + separate worker + nginx): a scan was processed by the worker container; websites pointing at `db:5432` and `api:8000` were refused.

## 4. Accessibility tests performed (the product itself)

- **axe-core via Playwright** (WCAG 2.0/2.1/2.2 A/AA + best practices) with zero violations required on: sign-in, registration, empty dashboard, add-website dialog, website detail, new scan, scan results, manual-review tab, scoring dialog, issue detail, dashboard with data, issues, scans, reports, monitoring, AI assistant, contrast checker, compare, settings, 404 page, mobile navigation and mobile contrast page.
- **Keyboard:** skip link is the first tab stop; WAI-ARIA tabs with arrow keys; `Escape` closes dialogs and returns focus; all actions are native buttons/links/inputs.
- **Forms:** visible labels, required indication in text, `aria-invalid` and `aria-describedby` for hints and errors (unit-tested and E2E-tested); errors announced via `role="alert"`; status messages via `role="status"`.
- **Reduced motion:** animations disabled under `prefers-reduced-motion` (E2E).
- **Mobile:** Pixel 7 viewport – menu button with `aria-expanded`, no horizontal overflow, axe clean.
- **ESLint `jsx-a11y`** passes on the whole frontend.

Requires manual testing (not done): screen readers (NVDA, JAWS, VoiceOver, TalkBack), Windows High Contrast / forced colours, 200 %/400 % zoom and text-spacing overrides on every page, speech input, and testing with disabled users. Passing automated checks does **not** make the product fully WCAG conformant.

## 5. Backend test results

`pytest -q` – **139 passed** on SQLite (189.9 s) and **139 passed** on PostgreSQL 16 (219.0 s). Suites: unit (contrast maths, scoring, WCAG mapping, URL safety, settings guards, CSV safety), auth, website/scan/issue/report/comparison/monitoring/analytics workflow with a real worker and browser, scanner engine and SSRF, AI (mocked providers and mocked HTTP transports), job reliability (engine crash, stale recovery, atomic claiming, cancellation).
`ruff check .` and `ruff format --check` – pass.
Migrations on PostgreSQL – `upgrade head`, `alembic check` (no drift), `downgrade base`, `upgrade head`, `downgrade base` – pass.

## 6. Frontend test results

- ESLint (incl. `jsx-a11y`) – pass. TypeScript (`tsc -b`) – pass.
- Vitest – **10 passed** (contrast algorithm and thresholds, formatting/query helpers, accessible field/tabs/badge primitives).
- Playwright E2E – **5 passed** (desktop + mobile; real backend, real scan of the local fixture site, axe on every page, PDF download, sign-out/in). The screenshot-capture spec is skipped unless `SCREENSHOTS=1`.

## 7. Production build result

`npm run build` – success (Vite 7). Largest chunks: charts 465 kB (132 kB gzip), app 413 kB (131 kB gzip); pages are lazy-loaded.
Docker – `backend/Dockerfile` and `frontend/Dockerfile` build successfully; the Compose stack starts and passes health checks.

## 8. Remaining risks

- Automated accessibility testing covers only part of WCAG; manual review is always needed (documented in-product and in reports).
- Login throttling is in-memory per API process; use a shared limiter if running several instances.
- During a scan, local processes could connect to the scan's `127.0.0.1` proxy port (still restricted to public destinations).
- Chromium runs with `--no-sandbox` inside containers; container isolation and the guarded proxy are the boundaries.
- Access/refresh tokens in `localStorage` (CSP-mitigated).
- A scanned page can tamper with axe-core results about itself.
- AI adapters are tested with mocked providers only; live provider calls were not made (no paid calls without authorisation).
- Render free plan: limited memory/CPU, sleeping service, expiring free database.

## 9. GitHub publication readiness

Ready: `.gitignore` excludes `.env`, databases, virtualenvs, `node_modules`, build output, test artefacts and browser binaries; `.env.example` contains placeholders only; the only credentials in the repository are throwaway local/CI database passwords in `docker-compose.yml` and the CI workflow. Required documents, licence, CI workflow, Dockerfiles, Blueprint and launchers are present.

## 10. Render deployment readiness

Ready for Blueprint deployment: Docker-based API (Chromium dependencies included, binds `0.0.0.0:$PORT`, migrations on start, `/health/ready` health check, proxy headers trusted), static frontend with SPA rewrite and CSP, PostgreSQL via `fromDatabase`, generated `SECRET_KEY`, restricted CORS, embedded worker because background workers have no free tier. Plan limits are documented in `render.yaml` and INSTRUCTION.md. Deployment status is recorded in the section below.

## 11. Deployment status

See the *Deployment* section of README.md for the live URLs once deployed. Until a live scan has been verified, the deployment must be treated as not verified.

## Not verified
- macOS launcher on real macOS hardware.
- Screen-reader and other assistive-technology testing.
- Live calls to OpenAI, Anthropic or Gemini.
