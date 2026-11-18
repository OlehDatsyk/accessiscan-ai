"""Playwright + axe-core scanning engine.

The engine is independent of the database: it yields ``PageResult`` objects through a callback and the
worker persists them. Each scan gets its own guarded proxy, its own browser process and a fresh
incognito context, all torn down in ``finally`` blocks.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import shutil
import tempfile
import time
import urllib.robotparser
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urlsplit

import httpx

from app import __version__
from app.config import get_settings
from app.scanner import url_safety
from app.scanner.heuristics import analyse_html
from app.scanner.proxy import GuardedProxy

log = logging.getLogger("accessiscan.engine")

AXE_PATH = Path(__file__).parent / "vendor" / "axe.min.js"
_AXE_SOURCE: str | None = None
USER_AGENT_SUFFIX = "AccessiScanBot/1.0 (+automated accessibility audit)"
MAX_NODES_PER_RULE = 50
MAX_SNIPPET = 1200
MAX_SELECTOR = 600
MAX_HTML_FOR_ANALYSIS = 3_000_000
_SKIP_EXT = re.compile(
    r"\.(pdf|zip|gz|tar|rar|7z|exe|dmg|msi|apk|iso|jpg|jpeg|png|gif|webp|svg|ico|bmp|tiff|mp3|mp4|m4a|wav|ogg|"
    r"webm|mov|avi|doc|docx|xls|xlsx|ppt|pptx|csv|json|xml|rss|atom|woff2?|ttf|eot|css|js)$",
    re.I,
)
_SKIP_PATH = re.compile(r"(log-?out|sign-?out|/wp-admin|/cart/add|/delete|unsubscribe)", re.I)

AXE_TAGS_DEFAULT = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]
AXE_TAGS_AAA = ["wcag2aaa"]


def axe_source() -> str:
    global _AXE_SOURCE
    if _AXE_SOURCE is None:
        _AXE_SOURCE = AXE_PATH.read_text(encoding="utf-8")
    return _AXE_SOURCE


def axe_version() -> str:
    m = re.search(r"axe v(\d+\.\d+\.\d+)", axe_source()[:200])
    return m.group(1) if m else "unknown"


def scanner_version() -> str:
    try:
        from importlib.metadata import version

        pw = version("playwright")
    except Exception:  # noqa: BLE001
        pw = "unknown"
    return f"AccessiScan {__version__}; axe-core {axe_version()}; Playwright {pw}; Chromium"


@dataclass
class ScanRequest:
    urls: list[str]
    mode: str = "single"  # single | list | crawl
    max_pages: int = 10
    max_depth: int = 2
    include_aaa: bool = False
    respect_robots: bool = True


@dataclass
class PageResult:
    url: str
    depth: int
    status: str = "ok"  # ok | failed | blocked | skipped
    final_url: str = ""
    http_status: int | None = None
    title: str = ""
    lang: str = ""
    error: str = ""
    load_time_ms: int | None = None
    violations: list[dict[str, Any]] = field(default_factory=list)
    incomplete: list[dict[str, Any]] = field(default_factory=list)
    passed_rules: list[str] = field(default_factory=list)
    incomplete_rules: list[str] = field(default_factory=list)
    inapplicable_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    heuristics: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ScanOutcome:
    pages: int = 0
    stopped_reason: str = ""
    blocked_requests: list[dict[str, str]] = field(default_factory=list)
    bytes_downloaded: int = 0
    robots_skipped: int = 0


PageCallback = Callable[[PageResult, int], Awaitable[None]]
CancelCheck = Callable[[], Awaitable[bool]]


def _trim_rule(rule: dict[str, Any]) -> dict[str, Any]:
    nodes = []
    for node in (rule.get("nodes") or [])[:MAX_NODES_PER_RULE]:
        target = node.get("target") or []
        selector = " ".join(t if isinstance(t, str) else " >>> ".join(map(str, t)) for t in target)
        nodes.append(
            {
                "selector": selector[:MAX_SELECTOR],
                "html": str(node.get("html") or "")[:MAX_SNIPPET],
                "failure_summary": str(node.get("failureSummary") or "")[:2000],
                "impact": node.get("impact"),
            }
        )
    return {
        "id": str(rule.get("id", ""))[:120],
        "impact": rule.get("impact"),
        "tags": [str(t) for t in (rule.get("tags") or [])][:40],
        "description": str(rule.get("description") or "")[:1000],
        "help": str(rule.get("help") or "")[:500],
        "help_url": str(rule.get("helpUrl") or "")[:1000],
        "nodes": nodes,
        "total_nodes": len(rule.get("nodes") or []),
    }


def normalise_link(href: str) -> str | None:
    if not href:
        return None
    href, _ = urldefrag(href)
    parts = urlsplit(href)
    if parts.scheme not in ("http", "https"):
        return None
    if _SKIP_EXT.search(parts.path or "") or _SKIP_PATH.search(parts.path or ""):
        return None
    return href


class ScanEngine:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def run(
        self,
        request: ScanRequest,
        on_page: PageCallback,
        should_cancel: CancelCheck,
        on_progress: Callable[[str, int, int], Awaitable[None]] | None = None,
    ) -> ScanOutcome:
        from playwright.async_api import async_playwright

        s = self.settings
        max_pages = max(1, min(request.max_pages, s.scan_max_pages, 50))
        max_depth = max(0, min(request.max_depth, s.scan_max_depth, 5))
        deadline = time.monotonic() + s.scan_timeout_seconds
        outcome = ScanOutcome()

        proxy = GuardedProxy(
            max_total_bytes=int(s.scan_max_total_mb * 1024 * 1024),
            max_page_bytes=int(s.scan_max_page_mb * 1024 * 1024),
        )
        await proxy.start()
        tmp_dir = tempfile.mkdtemp(prefix="accessiscan-")
        browser = None
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True,
                    downloads_path=tmp_dir,
                    args=[
                        f"--proxy-server={proxy.url}",
                        "--proxy-bypass-list=<-loopback>",
                        # Chromium must not resolve names itself; everything goes through the proxy.
                        "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1",
                        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                        "--webrtc-ip-handling-policy=disable_non_proxied_udp",
                        "--disable-dev-shm-usage",
                        "--disable-background-networking",
                        "--disable-component-update",
                        "--disable-default-apps",
                        "--disable-extensions",
                        "--disable-sync",
                        "--disable-domain-reliability",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--mute-audio",
                        "--disable-features=Translate,MediaRouter,OptimizationHints,DialMediaRouteProvider",
                        "--js-flags=--max-old-space-size=512",
                    ],
                )
                default_ua = await self._default_user_agent(browser)
                context = await browser.new_context(
                    accept_downloads=False,
                    service_workers="block",
                    java_script_enabled=True,
                    ignore_https_errors=False,
                    viewport={"width": 1280, "height": 900},
                    user_agent=f"{default_ua} {USER_AGENT_SUFFIX}",
                    permissions=[],
                    locale="en-GB",
                )
                context.set_default_timeout(s.scan_page_timeout_seconds * 1000)
                await context.add_init_script(
                    "(() => { for (const k of ['RTCPeerConnection','webkitRTCPeerConnection','RTCDataChannel']) "
                    "{ try { delete window[k]; window[k] = undefined; } catch (e) {} } })();"
                )
                await context.route("**/*", self._route_filter)

                robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
                queue: list[tuple[str, int]] = []
                seen: set[str] = set()
                for u in request.urls:
                    if u not in seen:
                        seen.add(u)
                        queue.append((u, 0))
                if request.mode != "crawl":
                    queue = queue[:max_pages]
                scope_origin: str | None = None
                scanned_finals: set[str] = set()

                while queue and outcome.pages < max_pages:
                    if time.monotonic() > deadline:
                        outcome.stopped_reason = "Maximum scan duration reached"
                        break
                    if await should_cancel():
                        outcome.stopped_reason = "Cancelled by user"
                        break
                    if proxy.stats.budget_exceeded:
                        outcome.stopped_reason = "Maximum total download size reached"
                        break
                    url, depth = queue.pop(0)
                    if on_progress:
                        await on_progress(f"Scanning {url[:200]}", outcome.pages, max_pages)

                    if request.mode == "crawl" and depth > 0 and request.respect_robots:
                        allowed = await self._robots_allows(url, robots, proxy.url)
                        if not allowed:
                            outcome.robots_skipped += 1
                            continue

                    result = await self._scan_page(context, proxy, url, depth, request, deadline)
                    if result.status == "ok" and result.final_url:
                        if result.final_url in scanned_finals:
                            continue  # redirect landed on an already-scanned page
                        scanned_finals.add(result.final_url)
                    outcome.pages += 1
                    if scope_origin is None and result.status == "ok":
                        scope_origin = result.final_url or url

                    links = result.metadata.pop("_links", [])
                    await on_page(result, outcome.pages)

                    if request.mode == "crawl" and result.status == "ok" and depth < max_depth and scope_origin:
                        for link in links:
                            norm = normalise_link(link)
                            if not norm or norm in seen:
                                continue
                            if not url_safety.same_origin(norm, scope_origin):
                                continue
                            seen.add(norm)
                            if len(seen) > max_pages * 20:
                                break
                            queue.append((norm, depth + 1))

                    if queue and s.scan_crawl_delay_ms:
                        await asyncio.sleep(s.scan_crawl_delay_ms / 1000)

                if not outcome.stopped_reason and queue and outcome.pages >= max_pages:
                    outcome.stopped_reason = f"Page limit reached ({max_pages})"
                with contextlib.suppress(Exception):
                    await context.close()
                with contextlib.suppress(Exception):
                    await browser.close()
        finally:
            await proxy.stop()
            shutil.rmtree(tmp_dir, ignore_errors=True)
        outcome.blocked_requests = proxy.stats.blocked[:50]
        outcome.bytes_downloaded = proxy.stats.bytes_total
        return outcome

    @staticmethod
    async def _default_user_agent(browser: Any) -> str:
        page = await browser.new_page()
        try:
            return str(await page.evaluate("navigator.userAgent")).replace("HeadlessChrome", "Chrome")
        finally:
            await page.close()

    @staticmethod
    async def _route_filter(route: Any) -> None:
        req = route.request
        url = req.url
        scheme = url.split(":", 1)[0].lower()
        if scheme in ("data", "blob", "about"):
            await route.continue_()
            return
        if scheme not in ("http", "https"):
            await route.abort("blockedbyclient")
            return
        if req.resource_type in ("media",):  # audio/video bytes are not needed for the audit
            await route.abort("blockedbyclient")
            return
        try:
            host = urlsplit(url).hostname or ""
            url_safety.check_host_name(url_safety.normalise_host(host))
        except url_safety.UnsafeURLError:
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    async def _robots_allows(
        self, url: str, cache: dict[str, urllib.robotparser.RobotFileParser | None], proxy_url: str
    ) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in cache:
            parser: urllib.robotparser.RobotFileParser | None = None
            try:
                async with httpx.AsyncClient(
                    proxy=proxy_url, timeout=10, follow_redirects=False, headers={"User-Agent": USER_AGENT_SUFFIX}
                ) as client:
                    resp = await client.get(origin + "/robots.txt")
                if resp.status_code == 200 and len(resp.content) < 512_000:
                    parser = urllib.robotparser.RobotFileParser()
                    parser.parse(resp.text.splitlines())
            except Exception:  # noqa: BLE001 - unreachable robots.txt means "no restrictions"
                parser = None
            cache[origin] = parser
        p = cache[origin]
        return True if p is None else p.can_fetch("AccessiScanBot", url)

    async def _scan_page(
        self, context: Any, proxy: GuardedProxy, url: str, depth: int, request: ScanRequest, deadline: float
    ) -> PageResult:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        result = PageResult(url=url, depth=depth)
        try:
            await asyncio.to_thread(url_safety.validate_target, url)
        except url_safety.UnsafeURLError as exc:
            result.status, result.error = "blocked", str(exc)
            return result

        proxy.reset_page_budget()
        page = await context.new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
        page.on("popup", lambda p: asyncio.ensure_future(p.close()))
        start = time.monotonic()
        try:
            remaining = max(5.0, deadline - time.monotonic())
            nav_timeout = min(self.settings.scan_page_timeout_seconds, remaining) * 1000
            try:
                response = await page.goto(url, wait_until="load", timeout=nav_timeout)
            except PlaywrightTimeout:
                response = None
                if page.url in ("about:blank", ""):
                    raise
            with contextlib.suppress(PlaywrightTimeout, PlaywrightError):
                await page.wait_for_load_state("networkidle", timeout=5000)
            result.load_time_ms = int((time.monotonic() - start) * 1000)
            result.final_url = page.url
            result.http_status = response.status if response is not None else None
            if response is not None:
                hops, req = 0, response.request
                while req.redirected_from is not None and hops <= 50:
                    hops, req = hops + 1, req.redirected_from
                result.metadata["redirects"] = hops
                if hops > self.settings.scan_max_redirects:
                    result.status, result.error = "failed", f"Too many redirects ({hops})"
                    return result

            # Re-validate where the browser actually ended up (redirects, JS navigation).
            try:
                await asyncio.to_thread(url_safety.validate_target, result.final_url)
            except url_safety.UnsafeURLError as exc:
                result.status, result.error = "blocked", f"Redirected to a blocked destination: {exc}"
                return result
            if result.http_status is not None and result.http_status >= 400:
                result.status, result.error = "failed", f"The page returned HTTP {result.http_status}"
                return result

            await self._inject_axe(page)
            tags = AXE_TAGS_DEFAULT + (AXE_TAGS_AAA if request.include_aaa else [])
            axe_timeout = max(10.0, min(90.0, deadline - time.monotonic()))
            raw = await asyncio.wait_for(
                page.evaluate(
                    """async (tags) => {
                        const r = await window.axe.run(document, {
                            runOnly: { type: 'tag', values: tags },
                            resultTypes: ['violations', 'incomplete'],
                            iframes: true, frameWaitTime: 5000, elementRef: false, performanceTimer: false,
                        });
                        return {
                            violations: r.violations, incomplete: r.incomplete,
                            passes: r.passes.map(p => p.id), inapplicable: r.inapplicable.length,
                            engine: r.testEngine && r.testEngine.version,
                        };
                    }""",
                    tags,
                ),
                timeout=axe_timeout,
            )
            result.violations = [_trim_rule(r) for r in raw.get("violations", [])]
            result.incomplete = [_trim_rule(r) for r in raw.get("incomplete", [])]
            result.passed_rules = sorted({str(p) for p in raw.get("passes", [])})
            result.incomplete_rules = sorted({r["id"] for r in result.incomplete})
            result.inapplicable_count = int(raw.get("inapplicable", 0))

            links = await page.evaluate("() => Array.from(document.links, a => a.href).filter(Boolean).slice(0, 2000)")
            html = await page.content()
            meta, heuristics = analyse_html(html[:MAX_HTML_FOR_ANALYSIS], result.final_url)
            result.title = meta.get("title", "")[:500]
            result.lang = meta.get("lang", "")[:40]
            meta["axe_version"] = raw.get("engine") or axe_version()
            meta["_links"] = links
            meta["redirects"] = result.metadata.get("redirects", 0)
            result.metadata = meta
            result.heuristics = heuristics
        except TimeoutError:
            result.status, result.error = "failed", "Timed out while analysing the page"
        except PlaywrightTimeout:
            result.status, result.error = "failed", "The page did not finish loading within the time limit"
        except PlaywrightError as exc:
            result.status, result.error = "failed", _friendly_browser_error(str(exc))
        finally:
            with contextlib.suppress(Exception):
                await page.close()
        return result

    @staticmethod
    async def _inject_axe(page: Any) -> None:
        src = axe_source()
        # evaluate() is not subject to the page's Content-Security-Policy (unlike a <script> tag).
        await page.evaluate(src)
        for frame in page.frames[1:20]:
            with contextlib.suppress(Exception):
                await frame.evaluate(src)


def _friendly_browser_error(msg: str) -> str:
    low = msg.lower()
    if "err_tunnel_connection_failed" in low or "err_proxy_connection_failed" in low or "403" in low:
        return "The connection was refused by the scanner's network security policy"
    if "err_name_not_resolved" in low:
        return "The host name could not be resolved"
    if "err_cert" in low or "ssl" in low:
        return "The site's TLS certificate is invalid"
    if "err_connection_refused" in low or "502" in low:
        return "The site refused the connection"
    if "err_aborted" in low:
        return "Navigation was aborted (the URL may trigger a download)"
    if "err_too_many_redirects" in low:
        return "Too many redirects"
    first = msg.strip().splitlines()[0] if msg.strip() else "Browser error"
    return first[:300]
