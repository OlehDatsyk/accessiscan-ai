# AccessiScan AI – Instructions

This guide explains how to run AccessiScan AI, how to use every part of the application, and how to deploy it.

## 1. Start the application

### Windows
1. Install **Python 3.12+** (tick *Add python.exe to PATH*) and **Node.js LTS**. Docker Desktop is optional.
2. Double-click **`Start App.bat`**.
3. The first run installs dependencies and the Chromium browser (a few minutes). Two windows open – *AccessiScan API* and *AccessiScan Web* – and the browser opens **http://localhost:5173**.

To stop: close the two server windows. PostgreSQL (if Docker was used) keeps running and keeps your data; stop it with `docker compose stop db`.

### macOS
1. Install Python 3.12+ and Node.js (e.g. `brew install python@3.12 node`). Docker Desktop is optional.
2. Double-click **`Start App (Mac).command`**. If macOS blocks it the first time, right-click → *Open*, or run `chmod +x "Start App (Mac).command"` in Terminal.
3. Stop with **Ctrl+C** in the Terminal window.

### Which database is used?
- **Docker running** → PostgreSQL in a container on `127.0.0.1:55432` (data in the `accessiscan-pgdata` volume).
- **No Docker** → SQLite file `backend/accessiscan-dev.db`.

The launchers apply migrations (additive only). They never delete files or reset data.

### Optional configuration
Copy `.env.example` to `backend/.env` and adjust it – for example to enable AI (see §3). Never commit `.env`.

## 2. Using AccessiScan AI

1. **Create an account** (*Create an account* on the sign-in page). Passwords need 10+ characters with upper- and lower-case letters and a number.
2. **Add a website** (*Websites → Add website*): name, URL, optional description. Only add sites you own or are authorised to test. Internal/private addresses are refused.
3. **Start a scan** (*New scan*):
   - *Single page* – the website URL.
   - *List of URLs* – up to 50 URLs on the same domain, one per line.
   - *Limited crawl* – follows same-site links up to a page and depth limit; robots.txt is respected by default.
   - *Include WCAG AAA rules* – optional extra rules.
4. **Watch progress** on the scan page (status, current URL, pages done). You can cancel a running scan.
5. **Review results**:
   - Score card with *How is this calculated?* and the *Score details* tab (per-rule deductions).
   - Counts by severity, passed checks, needs-review and manual checks.
   - *Issues* tab – filter by severity, type (violation / needs review), category, WCAG criterion and status; search; select rows for bulk status changes.
   - *Pages* tab – every scanned page with status, score, counts and load time.
   - *Manual review* tab – WCAG criteria that need human testing, with instructions.
6. **Work on an issue** (click its title): where it was found (page, selector, HTML snippet), WCAG mapping with links, built-in guidance, optional AI suggestion, status (*Open, In progress, Marked fixed, Ignored* – ignoring requires a reason), internal notes and history.
   - *Marked fixed* is your claim. The issue counts as **resolved** only when a later scan no longer detects it; if it is detected again it is flagged *Previously marked fixed – detected again*.
   - *Ignored* decisions (with reason) carry over to the next scan of the same website.
7. **Compare scans** – *Compare with previous* on a scan, or select two completed scans in a website's *Scan history*. Shows new / resolved / remaining issues, severity changes, score and passed-check changes.
8. **Reports** – PDF, CSV or DOCX from a scan page or the *Reports* page. Reports include the methodology, WCAG mapping, remediation, manual checklist and limitations, and state that they are not legal certification.
9. **Monitoring** – enable daily, weekly or monthly scans per website (*Monitoring* page or a website's *Monitoring* tab). Nothing runs on a schedule unless you enable it; disable it at any time.
10. **Notifications** – the bell icon shows completed/failed scans and regressions.
11. **Contrast checker** – enter HEX or `rgb()` colours (or pick them); see the ratio and AA/AAA results for normal and large text and non-text contrast, plus a suggested passing colour.
12. **Settings** – profile, notification preferences, password change (signs out all sessions), *Sign out of all devices*, account deletion, AI status.

## 3. Enabling AI features

AI is optional. Add to `backend/.env` (or the server environment):

```env
AI_PROVIDER=openai            # or anthropic / gemini
OPENAI_API_KEY=sk-...         # the key for the selected provider
AI_MODEL=                     # optional model override
AI_DAILY_REQUEST_LIMIT=40     # per user
```
Restart the API. Then:
- *Get AI suggestion* on an issue – explanation, affected users, recommended fix, before/after code, verification steps. Cached per issue; *Regenerate* asks again.
- *AI assistant* page – choose a scan (and optionally an issue) and ask questions such as "What should I fix first?".
- *Generate summary* on a scan – executive summary, priorities and quick wins.

AI output is always labelled as a suggestion, is based only on detected issues, and is never applied to your website automatically. Paid API usage is billed by your provider.

## 4. Running the tests

```bash
cd backend && .venv/Scripts/python -m pytest -q          # macOS/Linux: .venv/bin/python
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
cd frontend && npx playwright test                         # E2E + axe-core accessibility checks
```

## 5. Deploying to Render

AccessiScan AI ships a Blueprint (`render.yaml`) with three resources: **`accessiscan-ai-api`** (Docker web service with the embedded scan worker), **`accessiscan-ai-frontend`** (static site) and **`accessiscan-ai-db`** (PostgreSQL).

1. Push the repository to GitHub.
2. In the Render Dashboard choose **New → Blueprint**, select the repository and confirm. Render creates the database first, then the API (Docker build from `backend/Dockerfile`) and the static frontend.
3. Wait for the API's first deploy (the Playwright base image is large; the first build takes several minutes). Migrations run automatically on start.
4. Check `https://accessiscan-ai-api.onrender.com/health/ready` → `{"status":"ok","database":"ok",…}`.
5. Open `https://accessiscan-ai-frontend.onrender.com`, register and run a scan of a site you control.
6. Optional – AI: in the API service's *Environment* tab set `AI_PROVIDER` and the matching key (marked *sync: false*, so you enter them in the dashboard; never commit them).

If your service names (and therefore URLs) differ, update `CORS_ORIGINS`/`FRONTEND_URL` on the API and `VITE_API_URL` plus the CSP `connect-src` on the frontend, then redeploy.

### Sizing
| Plan | Suitability |
|---|---|
| Free web service (512 MB, 0.1 CPU, sleeps after ~15 min idle) | Demo: single-page scans work but are slow; first request after sleep takes ~1 minute; crawls of heavy pages may run out of memory |
| Starter (512 MB, more CPU, always on) | Light production use with single-page/short crawls |
| Standard (2 GB) or a separate worker | Regular crawls, `SCAN_MAX_CONCURRENCY` > 1 |

Free Render PostgreSQL databases expire after 30 days; upgrade or set `DATABASE_URL` to another PostgreSQL to keep data. To run a dedicated worker on a paid plan, uncomment `accessiscan-ai-worker` in `render.yaml` and set `RUN_EMBEDDED_WORKER=false` on the API.

### Storage
All persistent data – including generated reports – is stored in PostgreSQL, so Render's ephemeral filesystem is only used for per-scan browser temp files, which are deleted after each scan. No external object storage is required.

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| "The scanning browser is not installed on the server" | `python -m playwright install chromium` (Linux: `--with-deps`) |
| Port 8000 or 5173 in use | Set `API_PORT` / `WEB_PORT` before running the launcher |
| "Cannot reach the AccessiScan API" in the web app | Make sure the API window is running and `http://127.0.0.1:8000/health/ready` responds |
| Scan "failed" with a security-policy message | The target (or a redirect) resolves to a private/internal address or disallowed port – this is intentional |
| Scan stays "queued" | The worker is not running: keep `RUN_EMBEDDED_WORKER=true` or start `python -m app.worker` |
| AI buttons disabled | Set `AI_PROVIDER` and the matching API key on the server and restart |
