# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] – 2026-11-18

### Added
- FastAPI backend (`/api/v1`) with SQLAlchemy 2 models, Alembic migrations, PostgreSQL and SQLite support.
- Accounts: registration, login, rotating refresh tokens with reuse detection, logout, sign-out everywhere, profile, notification preferences, password change, account deletion.
- Website management with SSRF-safe URL validation, archiving, deletion, analytics and monitoring settings.
- Scanning engine: Playwright + Chromium + axe-core 4.14; single page, URL list and limited same-site crawl with page/depth/time/size limits and robots.txt support.
- Guarded per-scan egress proxy with IP pinning (DNS-rebinding protection), download budgets and private-network blocking for every browser connection.
- Database-backed job queue worker (embedded or standalone) with atomic claiming, heartbeats, stale-job recovery and a monitoring scheduler.
- WCAG 2.2 reference data and tag-based mapping; best-practice labelling; manual-review checklist.
- Transparent scoring model with per-page deduction breakdown.
- Issue management: filters, search, statuses with mandatory ignore reasons, notes, history, bulk updates, regression detection and carry-over of ignored decisions.
- Scan comparison (new / resolved / remaining / severity changes) with persisted comparison records.
- AI provider layer for OpenAI, Anthropic and Gemini with validated JSON output, prompt-injection containment, caching, limits and usage logs; built-in non-AI guidance.
- Contrast checker (API + UI) with correct WCAG thresholds.
- PDF, CSV and DOCX reports with methodology, limitations and formula-injection protection.
- Dashboard, analytics, notifications and activity log computed from stored records.
- Accessible React frontend (Tailwind, Radix Dialog, Recharts with data-table alternatives, keyboard tabs, skip link, focus management, reduced motion).
- Test suites: 139 backend tests (incl. real-browser scans and SSRF tests, run on SQLite and PostgreSQL), 10 frontend unit tests, Playwright E2E with axe-core on every page (desktop + mobile).
- Docker images, Docker Compose stack with a dedicated worker, Render Blueprint, GitHub Actions CI, Windows and macOS launchers, documentation.

### Fixed during the pre-release audit
- Legacy IPv4 host notations (e.g. `127.1`) are now decoded like browsers do before the IP check.
- Sign-in no longer bounced new users back to the login page (query-cache handling).
- Dialogs now return focus to the control that opened them.
- Lazy-loaded pages keep the layout and `<main>` landmark while loading.
- Charts are inert for assistive technology (data tables provide the content); stat cards use valid description-list markup; login/registration panels are inside landmarks; an in-progress scan has a section heading.
- Issue lists are paginated in SQL (also for WCAG filters); report listings no longer load file contents.
- Local PostgreSQL moved to port 55432 to avoid conflicts; Windows launcher works without an interactive console.
