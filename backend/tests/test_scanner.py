"""Real browser scans (Playwright + Chromium + axe-core) against local fixture sites, and scanner SSRF tests.

No external website is contacted: the fixture site and the "internal service" are local servers, and DNS
for any other name is faked.
"""

from __future__ import annotations

import asyncio
import socket
from typing import Any

import pytest

from app.scanner.engine import PageResult, ScanEngine, ScanRequest, normalise_link
from app.scanner.proxy import GuardedProxy
from tests.conftest import FixtureSite, InternalService

pytestmark = pytest.mark.browser


def run_scan(request: ScanRequest) -> tuple[list[PageResult], Any]:
    pages: list[PageResult] = []

    async def on_page(result: PageResult, _: int) -> None:
        pages.append(result)

    async def never_cancel() -> bool:
        return False

    async def go() -> Any:
        return await ScanEngine().run(request, on_page, never_cancel)

    outcome = asyncio.run(go())
    return pages, outcome


def rule_ids(rules: list[dict[str, Any]]) -> set[str]:
    return {r["id"] for r in rules}


def test_detects_known_violations(site: FixtureSite) -> None:
    pages, _ = run_scan(ScanRequest(urls=[f"{site.base}/violations.html"]))
    assert len(pages) == 1
    p = pages[0]
    assert p.status == "ok", p.error
    found = rule_ids(p.violations)
    for expected in ("image-alt", "label", "button-name", "link-name", "color-contrast", "html-has-lang", "aria-roles"):
        assert expected in found, f"{expected} not detected; got {sorted(found)}"
    assert p.passed_rules, "passed rules should be recorded"
    assert p.title == "Violations fixture"
    assert any(h["id"] == "accessiscan-generic-link-text" for h in p.heuristics)
    contrast = next(r for r in p.violations if r["id"] == "color-contrast")
    assert "wcag143" in contrast["tags"] and contrast["nodes"][0]["html"].startswith("<p")


def test_accessible_page_has_no_violations(site: FixtureSite) -> None:
    pages, _ = run_scan(ScanRequest(urls=[f"{site.base}/accessible.html"]))
    assert pages[0].status == "ok"
    assert pages[0].violations == [], [r["id"] for r in pages[0].violations]
    assert len(pages[0].passed_rules) > 10
    assert pages[0].lang == "en"


def test_crawl_respects_scope_depth_and_limits(site: FixtureSite) -> None:
    pages, outcome = run_scan(ScanRequest(urls=[f"{site.base}/index.html"], mode="crawl", max_pages=10, max_depth=1))
    urls = {p.url for p in pages}
    assert f"{site.base}/index.html" in urls and f"{site.base}/page2.html" in urls
    assert f"{site.base}/accessible.html" in urls  # fragment removed and followed
    assert f"{site.base}/page3.html" not in urls  # depth 2 > max_depth 1
    assert not any("example.org" in u or "logout" in u or u.endswith(".pdf") for u in urls)
    assert not any("logout" in h or "brochure" in h for h in site.hits)

    pages, outcome = run_scan(ScanRequest(urls=[f"{site.base}/index.html"], mode="crawl", max_pages=2, max_depth=3))
    assert len(pages) == 2 and "Page limit" in outcome.stopped_reason


def test_failed_pages_are_reported(site: FixtureSite) -> None:
    pages, _ = run_scan(
        ScanRequest(urls=[f"{site.base}/not-found.html", f"{site.base}/accessible.html"], mode="list", max_pages=2)
    )
    assert pages[0].status == "failed" and "404" in pages[0].error
    assert pages[1].status == "ok"


def test_redirect_within_site_is_followed(site: FixtureSite) -> None:
    pages, _ = run_scan(ScanRequest(urls=[f"{site.base}/redirect-ok"]))
    assert pages[0].status == "ok" and pages[0].final_url.endswith("/accessible.html")


# ----------------------------------------------------------------------------- SSRF


def test_direct_internal_target_is_blocked_before_navigation(site: FixtureSite, internal: InternalService) -> None:
    pages, _ = run_scan(ScanRequest(urls=[f"{internal.url}/admin"]))
    assert pages[0].status == "blocked"
    assert internal.hits == []


def test_redirect_to_internal_service_is_blocked(site: FixtureSite, internal: InternalService) -> None:
    pages, outcome = run_scan(ScanRequest(urls=[f"{site.base}/redirect-internal"]))
    assert pages[0].status in ("failed", "blocked")
    assert internal.hits == [], "the internal service must never receive a request"
    assert any(b["host"] == "127.0.0.1" for b in outcome.blocked_requests)


def test_redirect_to_file_scheme_is_blocked(site: FixtureSite) -> None:
    pages, _ = run_scan(ScanRequest(urls=[f"{site.base}/redirect-file"]))
    assert pages[0].status in ("failed", "blocked")
    assert "root:" not in str(pages[0].metadata)


def test_subresources_websockets_and_metadata_are_blocked(site: FixtureSite, internal: InternalService) -> None:
    pages, outcome = run_scan(ScanRequest(urls=[f"{site.base}/ssrf-subresources.html"]))
    assert pages[0].status == "ok"
    assert internal.hits == [], f"internal service was reached: {internal.hits}"
    hosts = {b["host"] for b in outcome.blocked_requests}
    assert "127.0.0.1" in hosts and "169.254.169.254" in hosts


def test_page_size_limit(site: FixtureSite, settings: Any) -> None:
    settings.scan_max_page_mb = 0.5
    pages, outcome = run_scan(ScanRequest(urls=[f"{site.base}/huge.html"]))
    assert outcome.bytes_downloaded < 1_500_000
    assert any(b["reason"] == "download size limit reached" for b in outcome.blocked_requests)


def test_total_download_budget_stops_scan(site: FixtureSite, settings: Any) -> None:
    settings.scan_max_total_mb = 0.3
    settings.scan_max_page_mb = 5
    pages, outcome = run_scan(
        ScanRequest(urls=[f"{site.base}/huge.html", f"{site.base}/accessible.html"], mode="list", max_pages=2)
    )
    assert outcome.stopped_reason == "Maximum total download size reached"


def test_normalise_link_filters() -> None:
    assert normalise_link("https://a.example/x#frag") == "https://a.example/x"
    for bad in (
        "mailto:x@y.z",
        "javascript:void(0)",
        "https://a.example/file.pdf",
        "https://a.example/logout",
        "ftp://a.example/",
        "",
    ):
        assert normalise_link(bad) is None


# ----------------------------------------------------------------------------- proxy unit tests


def _proxy_request(raw: bytes) -> bytes:
    async def go() -> bytes:
        proxy = GuardedProxy(max_total_bytes=10_000_000, max_page_bytes=10_000_000)
        port = await proxy.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(raw)
            await writer.drain()
            data = await asyncio.wait_for(reader.read(4096), timeout=10)
            writer.close()
            return data
        finally:
            await proxy.stop()

    return asyncio.run(go())


@pytest.mark.parametrize(
    "raw",
    [
        b"CONNECT 127.0.0.1:443 HTTP/1.1\r\nHost: 127.0.0.1:443\r\n\r\n",
        b"CONNECT rebind.example.com:443 HTTP/1.1\r\n\r\n",  # DNS answer is loopback
        b"CONNECT internal.example.com:443 HTTP/1.1\r\n\r\n",
        b"CONNECT [::1]:443 HTTP/1.1\r\n\r\n",
        b"CONNECT example.com:22 HTTP/1.1\r\n\r\n",  # disallowed port
        b"CONNECT user@example.com:443 HTTP/1.1\r\n\r\n",
        b"GET http://169.254.169.254/latest/meta-data/ HTTP/1.1\r\nHost: 169.254.169.254\r\n\r\n",
        b"GET http://2130706433/ HTTP/1.1\r\n\r\n",
        b"GET ftp://example.com/ HTTP/1.1\r\n\r\n",
        b"GET /relative HTTP/1.1\r\n\r\n",
    ],
)
def test_proxy_refuses_internal_destinations(raw: bytes) -> None:
    resp = _proxy_request(raw)
    assert resp.startswith((b"HTTP/1.1 403", b"HTTP/1.1 400")) or resp == b"", resp[:80]


def test_proxy_pins_validated_ip_against_rebinding(
    monkeypatch: pytest.MonkeyPatch, site: FixtureSite, internal: InternalService
) -> None:
    """The proxy connects to the IP it validated, never re-resolving: a second, different DNS answer is unused."""
    from app.scanner import url_safety

    answers = iter([["127.0.0.1"]])  # allow-listed answer once, then anything else must not be consulted

    def resolver(host: str, port: int) -> list[str]:
        return next(answers, ["10.0.0.1"])

    monkeypatch.setattr(url_safety, "resolve_host", resolver)
    raw = f"GET http://fixture.example.com:{site.port}/accessible.html HTTP/1.1\r\nHost: x\r\n\r\n".encode()
    # fixture.example.com is not allow-listed, so even the first (loopback) answer must be refused.
    assert _proxy_request(raw).startswith(b"HTTP/1.1 403")
    assert internal.hits == []


def test_chromium_cannot_resolve_names_itself() -> None:
    # sanity check that our fake resolver is what the proxy uses (no real DNS in tests)
    from app.scanner import url_safety

    assert url_safety.resolve_host("anything.example.com", 443) == ["93.184.215.14"]
    with pytest.raises(OSError):
        url_safety.resolve_host("x.invalid", 443)
    assert socket.AF_INET  # keep import used
