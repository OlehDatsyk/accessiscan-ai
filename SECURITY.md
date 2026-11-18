# Security

## Reporting a vulnerability

Please report security problems privately through GitHub's **"Report a vulnerability"** (Security → Advisories) on this repository rather than in a public issue. Include steps to reproduce and the impact you observed. Do not test against deployments you do not own.

## Threat model

AccessiScan AI accepts URLs from users and opens them in a real browser on the server. The main risks are:

1. **Server-side request forgery (SSRF)** – using the scanner to reach internal services, cloud metadata endpoints, databases or local files.
2. **Abuse of the scanner** – using it to load arbitrary third-party sites aggressively or to exhaust server resources.
3. **Cross-user data access** – reading or modifying another user's websites, scans, issues or reports.
4. **Account compromise** – credential stuffing, token theft or forgery.
5. **Prompt injection** – scanned page content trying to steer the AI layer.
6. **Malicious content in reports** – e.g. spreadsheet formula injection in CSV exports, HTML/script injection from scanned snippets.

## Scanner: defence in depth

### Layer 1 – URL validation (`backend/app/scanner/url_safety.py`)
Applied when a website is created/edited, when a scan is created, before each page navigation and again on the final URL after redirects:

- Only `http`/`https`; URLs with credentials, control characters, backslashes or > 2048 characters are refused.
- Ports must be in `SCAN_ALLOWED_PORTS` (default 80, 443, 8080, 8443).
- Host names `localhost`, `*.localhost`, `*.local`, `*.internal`, `*.lan`, `*.home.arpa`, `metadata.google.internal` and similar are refused.
- Legacy numeric IPv4 hosts (`127.1`, `2130706433`, `0x7f.1`, `0177.0.0.1`) are decoded with the WHATWG algorithm browsers use.
- The host is resolved; **every** returned address must be globally routable unicast. Refused: loopback, RFC 1918, link-local (incl. `169.254.169.254`), CGNAT `100.64/10` (incl. `100.100.100.200`), `0.0.0.0/8`, documentation/benchmark ranges, multicast, reserved, ULA `fc00::/7` (incl. `fd00:ec2::254`), IPv6 link-local, and IPv4-mapped, NAT64, 6to4 and Teredo encodings of private addresses.
- Scan URLs must belong to the website's own domain.

### Layer 2 – network enforcement (`backend/app/scanner/proxy.py`)
String validation alone cannot stop redirects, sub-resources, JavaScript `fetch`, WebSockets, iframes or DNS rebinding. Therefore:

- Each scan starts its own proxy on `127.0.0.1`. Chromium is launched with `--proxy-server`, with the implicit loopback bypass removed (`--proxy-bypass-list=<-loopback>`) and with its own DNS resolution disabled (`--host-resolver-rules=MAP * ~NOTFOUND`), so every connection must go through the proxy.
- For each connection the proxy repeats the port/host/IP checks, resolves the name itself and **connects to the validated IP address** – a different DNS answer later (rebinding) is never used.
- Per-page and per-scan download budgets, connection and idle timeouts are enforced at the byte level (also for HTTPS tunnels).
- WebRTC is disabled (`--force-webrtc-ip-handling-policy=disable_non_proxied_udp` plus removal of `RTCPeerConnection`) because it can bypass HTTP proxies.
- A Playwright route filter additionally aborts non-HTTP schemes, media downloads and blocked host names.

The automated tests (`backend/tests/test_scanner.py`) run a local "internal service" and prove it receives **zero** requests when targeted directly, via HTTP redirects, `file://` redirects, `<img>`, `<iframe>`, `fetch()`, WebSocket and metadata-IP requests, and that the proxy refuses rebinding, loopback, IPv6-loopback, private, disallowed-port and legacy-IPv4 destinations.

### Browser isolation and resource limits
- A separate Chromium process and a fresh incognito context per scan; closed in `finally` blocks. No persistent profile, no cookies shared between scans or users.
- Downloads disabled (`accept_downloads=False`), service workers blocked, dialogs dismissed, pop-ups closed, media requests dropped; a per-scan temporary directory is deleted afterwards.
- Hard limits: pages per scan (≤ 50), crawl depth (≤ 5), total scan time, per-page timeout, redirects, page/total download size, worker concurrency, per-user active scans and per-user hourly scans. A politeness delay is applied between crawled pages and robots.txt is honoured for crawls.
- In Docker, Chromium runs as the unprivileged `pwuser` with `--no-sandbox` (Chromium's own sandbox needs kernel privileges most container platforms do not grant). The container is the isolation boundary; the guarded proxy prevents network pivoting.
- The scanner never sends application credentials, cookies or internal URLs to scanned sites; it does not attempt to bypass logins, CAPTCHAs or paywalls.

### Development-only allow-list
`SCANNER_ALLOW_HOSTS` lets developers scan a local test site (`host:port` pairs). It is ignored in code and **refused at startup** when `ENVIRONMENT=production`.

## Accounts and sessions
- Passwords: Argon2id (`argon2-cffi`), minimum 10 characters with mixed case and digits; constant-time verification with a dummy hash for unknown users (no user enumeration via timing or messages).
- Access tokens: HS256 JWT, 30 minutes, explicit algorithm allow-list, required `exp/iat/sub/aud/iss`, `type=access` and a per-user `token_version` (bumped on password change and "sign out everywhere").
- Refresh tokens: random 384-bit values stored only as SHA-256 hashes, 7 days, **rotated on every use**; re-use of a rotated token revokes the whole token family.
- Login throttling per IP + e-mail and registration throttling per IP (in-memory, per process – see residual risks).
- `SECRET_KEY` must be ≥ 32 characters in production; the default development key is refused.

## Authorisation and data isolation
- Every user-owned table carries `owner_id`; every query filters on the authenticated user. Requests for another user's resource return **404** (IDs cannot be probed).
- Tested in `test_workflow.py::test_user_data_isolation` across websites, scans, pages, issues, notes, status changes, reports, monitoring, comparisons and AI endpoints.
- Organisation/team sharing is not implemented, so there is no cross-user sharing path.

## API hardening
- CORS restricted to configured origins (wildcards refused in production); no credentialed CORS (bearer tokens only).
- Security headers on all responses (`X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, restrictive CSP for API responses, HSTS in production, `Cache-Control: no-store` for API data).
- Request bodies over 1 MB are rejected; all inputs validated with Pydantic; generic error responses without stack traces.

## Frontend
- Scanned HTML snippets are always rendered as text (`<code>`), never as HTML. No `dangerouslySetInnerHTML` is used.
- Production CSP (`render.yaml`, `frontend/nginx.conf`): `script-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`.
- Tokens are stored in `localStorage` (trade-off: simple cross-origin deployment; mitigated by CSP and the absence of HTML rendering – an XSS bug would expose tokens).

## AI layer
- API keys only in server environment variables; never sent to the browser, never logged. Keys are sent in headers, not URLs.
- Only issues detected and stored for the requesting user are sent to the provider.
- Scanned content is JSON-encoded in a `<scan_data>` block that cannot be closed early; the system prompt declares it untrusted data.
- Output is parsed as JSON and validated with Pydantic; WCAG references are filtered to the criteria the engine mapped and referenced issue IDs to the issues in context. Invalid output is rejected.
- Timeouts, output-token caps, per-user daily limits, per-issue caching and a usage log limit cost.

## Reports
- Stored in the database (not the public filesystem), downloadable only by their owner, served with `Content-Disposition: attachment`, `no-store` and `nosniff`.
- CSV cells beginning with `=`, `+`, `-`, `@`, tab or carriage return are prefixed to prevent formula injection.
- Every report states that it is an automated assessment, not legal certification.

## Secrets in the repository
- `.env` files are git-ignored; `.env.example` contains placeholders only.
- `docker-compose.yml` and the CI workflow contain throwaway credentials for local/CI databases only.

## Residual risks
- **Local proxy port**: during a scan, other processes on the same host could connect to the scan's proxy port on `127.0.0.1`; it still only reaches public addresses. Run the scanner on a dedicated host/container.
- **In-memory throttling**: login/registration throttling is per API process; behind several instances use a shared rate limiter (e.g. Redis or the platform's WAF). Scan and AI limits are database-backed and global.
- **Page-controlled results**: a scanned page's JavaScript shares the main world with axe-core and could falsify its *own* results. This only affects the site owner's own report.
- **`--no-sandbox`** inside containers (see above).
- **localStorage tokens** (see Frontend).
- Running on a host without outbound firewalling is less safe than running with an egress policy that blocks private ranges at the network level as well; where possible add one (e.g. Kubernetes NetworkPolicy, cloud firewall).
