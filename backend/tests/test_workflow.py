"""End-to-end API workflow: websites -> scans (real worker + browser) -> issues -> comparison -> reports,
plus data isolation between users, background-job reliability and monitoring."""

from __future__ import annotations

import asyncio
import csv
import io
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.db import session_factory, utcnow
from app.models import MonitoringConfig, Scan
from app.worker import Worker
from tests.conftest import FixtureSite


def run_worker() -> int:
    return asyncio.run(Worker().run_once())


def add_site(client: TestClient, user: dict[str, Any], url: str, name: str = "Fixture") -> dict[str, Any]:
    r = client.post("/api/v1/websites", headers=user["headers"], json={"name": name, "url": url, "description": "d"})
    assert r.status_code == 201, r.text
    return r.json()


def start_scan(client: TestClient, user: dict[str, Any], website_id: str, **kw: Any) -> dict[str, Any]:
    r = client.post("/api/v1/scans", headers=user["headers"], json={"website_id": website_id, **kw})
    assert r.status_code == 202, r.text
    return r.json()


# ----------------------------------------------------------------------------- websites


def test_website_crud_and_validation(client: TestClient, user: dict[str, Any]) -> None:
    h = user["headers"]
    for bad in (
        "http://localhost:8000",
        "file:///etc/passwd",
        "http://10.0.0.1",
        "javascript:alert(1)",
        "http://internal.example.com",
    ):
        r = client.post("/api/v1/websites", headers=h, json={"name": "x", "url": bad})
        assert r.status_code == 422, bad
    site = add_site(client, user, "example.com/shop", "Shop")
    assert site["url"] == "https://example.com/shop"
    r = client.patch(f"/api/v1/websites/{site['id']}", headers=h, json={"name": "Shop 2", "url": "https://example.com"})
    assert r.json()["name"] == "Shop 2"
    assert (
        client.patch(f"/api/v1/websites/{site['id']}", headers=h, json={"url": "http://127.0.0.1"}).status_code == 422
    )
    assert client.patch(f"/api/v1/websites/{site['id']}", headers=h, json={"is_archived": True}).json()["is_archived"]
    assert client.get("/api/v1/websites", headers=h).json() == []
    assert len(client.get("/api/v1/websites?include_archived=true", headers=h).json()) == 1
    assert client.post("/api/v1/scans", headers=h, json={"website_id": site["id"]}).status_code == 400
    assert client.delete(f"/api/v1/websites/{site['id']}", headers=h).status_code == 204
    assert client.get(f"/api/v1/websites/{site['id']}", headers=h).status_code == 404


def test_scan_urls_must_belong_to_website(client: TestClient, user: dict[str, Any]) -> None:
    site = add_site(client, user, "https://example.com")
    r = client.post(
        "/api/v1/scans",
        headers=user["headers"],
        json={"website_id": site["id"], "mode": "list", "urls": ["https://other.example.net/"]},
    )
    assert r.status_code == 422
    r = client.post(
        "/api/v1/scans",
        headers=user["headers"],
        json={"website_id": site["id"], "mode": "list", "urls": ["https://www.example.com/a", "http://10.0.0.1/"]},
    )
    assert r.status_code == 422


def test_scan_rate_limits(client: TestClient, user: dict[str, Any], settings: Any) -> None:
    settings.scan_user_max_active = 1
    site = add_site(client, user, "https://example.com")
    start_scan(client, user, site["id"])
    r = client.post("/api/v1/scans", headers=user["headers"], json={"website_id": site["id"]})
    assert r.status_code == 429


# ----------------------------------------------------------------------------- full workflow


@pytest.mark.browser
def test_full_scan_workflow(client: TestClient, user: dict[str, Any], site: FixtureSite) -> None:
    h = user["headers"]
    ws = add_site(client, user, f"{site.base}/violations.html")
    scan = start_scan(client, user, ws["id"])
    assert scan["status"] == "queued"
    assert run_worker() == 1
    scan = client.get(f"/api/v1/scans/{scan['id']}", headers=h).json()
    assert scan["status"] == "completed", scan["error_message"]
    assert 0 <= scan["score"] < 100
    s = scan["summary"]
    assert s["pages_scanned"] == 1 and s["by_impact"]["critical"] > 0 and s["passed_checks"] > 0
    assert "axe-core" in scan["scanner_version"] and "Playwright" in scan["scanner_version"]

    pages = client.get(f"/api/v1/scans/{scan['id']}/pages", headers=h).json()
    assert pages[0]["status"] == "ok" and pages[0]["score"] == scan["score"]
    assert pages[0]["page_metadata"]["score_breakdown"]

    # score is reproducible from the stored breakdown (transparency)
    deductions = sum(b["deduction"] for b in pages[0]["page_metadata"]["score_breakdown"])
    assert scan["score"] == pytest.approx(max(0, 100 - deductions), abs=0.11)

    issues = client.get(f"/api/v1/issues?scan_id={scan['id']}&page_size=200", headers=h).json()
    assert issues["total"] == len(issues["items"]) > 0
    first = issues["items"][0]
    assert first["impact"] == "critical"  # sorted by severity
    contrast = next(i for i in issues["items"] if i["rule_id"] == "color-contrast")
    assert (
        contrast["wcag_criteria"] == ["1.4.3"] and contrast["wcag_level"] == "AA" and not contrast["is_best_practice"]
    )
    region = [i for i in issues["items"] if i["rule_id"] in ("region", "landmark-one-main", "heading-order")]
    assert region and all(i["is_best_practice"] and i["wcag_criteria"] == [] for i in region)
    heur = next(i for i in issues["items"] if i["rule_id"] == "accessiscan-generic-link-text")
    assert heur["kind"] == "needs_review" and heur["source"] == "accessiscan-heuristic"

    # filters
    crit = client.get(f"/api/v1/issues?scan_id={scan['id']}&impact=critical", headers=h).json()
    assert crit["total"] > 0 and all(i["impact"] == "critical" for i in crit["items"])
    by_wcag = client.get(f"/api/v1/issues?scan_id={scan['id']}&wcag=1.4.3", headers=h).json()
    assert by_wcag["total"] >= 1 and all("1.4.3" in i["wcag_criteria"] for i in by_wcag["items"])
    by_cat = client.get(f"/api/v1/issues?scan_id={scan['id']}&category=color", headers=h).json()
    assert all(i["category"] == "color" for i in by_cat["items"])
    search = client.get(f"/api/v1/issues?scan_id={scan['id']}&q=contrast", headers=h).json()
    assert any(i["rule_id"] == "color-contrast" for i in search["items"])
    review = client.get(f"/api/v1/issues?scan_id={scan['id']}&kind=needs_review", headers=h).json()
    assert all(i["kind"] == "needs_review" for i in review["items"])
    facets = client.get(f"/api/v1/issues/facets?scan_id={scan['id']}", headers=h).json()
    assert facets["impact"]["critical"] == s["by_impact"]["critical"]
    paged = client.get(f"/api/v1/issues?scan_id={scan['id']}&page_size=2&page=2", headers=h).json()
    assert len(paged["items"]) == 2 and paged["page"] == 2

    # issue detail, status management, notes, history
    img = next(i for i in issues["items"] if i["rule_id"] == "image-alt")
    detail = client.get(f"/api/v1/issues/{img['id']}", headers=h).json()
    assert detail["guidance"]["source"] == "built-in" and detail["wcag_details"][0]["number"] == "1.1.1"
    assert (
        client.patch(f"/api/v1/issues/{img['id']}/status", headers=h, json={"status": "ignored"}).status_code == 422
    )  # reason required
    r = client.patch(f"/api/v1/issues/{img['id']}/status", headers=h, json={"status": "marked_fixed"})
    assert r.json()["status"] == "marked_fixed" and r.json()["history"][0]["to_status"] == "marked_fixed"
    contrast_id = contrast["id"]
    client.patch(
        f"/api/v1/issues/{contrast_id}/status",
        headers=h,
        json={"status": "ignored", "reason": "Brand colour approved by design review"},
    )
    note = client.post(f"/api/v1/issues/{img['id']}/notes", headers=h, json={"body": "Assigned to front-end team"})
    assert note.status_code == 201
    assert (
        client.get(f"/api/v1/issues/{img['id']}", headers=h).json()["notes"][0]["body"] == "Assigned to front-end team"
    )

    # reports
    for fmt, magic in (("pdf", b"%PDF"), ("csv", b"\xef\xbb\xbf"), ("docx", b"PK")):
        rep = client.post("/api/v1/reports", headers=h, json={"scan_id": scan["id"], "format": fmt})
        assert rep.status_code == 201, rep.text
        dl = client.get(f"/api/v1/reports/{rep.json()['id']}/download", headers=h)
        assert dl.status_code == 200 and dl.content.startswith(magic)
        assert "attachment" in dl.headers["content-disposition"]
        if fmt == "csv":
            rows = list(csv.reader(io.StringIO(dl.content.decode("utf-8-sig"))))
            assert "not a legal certification" in rows[0][0]
            header = rows[1]
            data = [dict(zip(header, row, strict=False)) for row in rows[2:]]
            assert len(data) == issues["total"]
            assert any(d["rule_id"] == "color-contrast" and d["wcag_criteria"] == "1.4.3" for d in data)
            assert any(d["status"] == "ignored" for d in data)
        if fmt == "pdf":
            assert len(dl.content) > 3000

    # re-scan after the site changed: comparison, carry-over and regression detection
    second = start_scan(client, user, ws["id"])
    run_worker()
    second = client.get(f"/api/v1/scans/{second['id']}", headers=h).json()
    assert second["status"] == "completed"
    assert second["summary"]["carry_over"]["carried_ignored"] >= 1
    assert second["summary"]["carry_over"]["regressed"] >= 1  # image marked fixed but still detected
    issues2 = client.get(f"/api/v1/issues?scan_id={second['id']}&page_size=200", headers=h).json()["items"]
    assert any(i["rule_id"] == "image-alt" and i["regressed"] and i["status"] == "open" for i in issues2)
    assert any(i["rule_id"] == "color-contrast" and i["status"] == "ignored" for i in issues2)
    cmp = client.get(f"/api/v1/scans/{scan['id']}/compare/{second['id']}", headers=h).json()
    assert cmp["counts"]["new"] == 0 and cmp["counts"]["resolved"] == 0 and cmp["counts"]["remaining"] > 0
    assert cmp["score_change"] == 0 and "approximate" in cmp["note"]

    # dashboard & analytics are computed from records
    dash = client.get("/api/v1/dashboard", headers=h).json()
    assert dash["websites"] == 1 and dash["total_scans"] == 2 and dash["average_score"] == second["score"]
    assert dash["critical_issues"] == second["summary"]["by_impact"]["critical"]
    an = client.get("/api/v1/analytics", headers=h).json()
    assert len(an["score_trend"]) == 2 and sum(r["websites"] for r in an["score_ranges"]) == 1
    wa = client.get(f"/api/v1/websites/{ws['id']}/analytics", headers=h).json()
    assert len(wa["trend"]) == 2
    notes = client.get("/api/v1/notifications", headers=h).json()
    assert any(n["kind"] == "scan_completed" for n in notes)
    assert any(n["kind"] == "regression" for n in notes)


@pytest.mark.browser
def test_scan_comparison_detects_new_and_resolved(client: TestClient, user: dict[str, Any], site: FixtureSite) -> None:
    h = user["headers"]
    site.set_page(
        "/dynamic.html",
        "<!doctype html><html lang='en'><head><title>v1</title></head><body><main>"
        "<h1>Dynamic</h1><img src='data:image/gif;base64,R0lGODlhAQABAAAAACw=' id='hero'>"
        "<input id='q' type='text'></main></body></html>",
    )
    ws = add_site(client, user, f"{site.base}/dynamic.html")
    s1 = start_scan(client, user, ws["id"])
    run_worker()
    site.set_page(
        "/dynamic.html",
        "<!doctype html><html lang='en'><head><title>v2</title></head><body><main>"
        "<h1>Dynamic</h1><img src='data:image/gif;base64,R0lGODlhAQABAAAAACw=' id='hero' alt='Hero'>"
        "<input id='q' type='text'><button id='go'></button></main></body></html>",
    )
    s2 = start_scan(client, user, ws["id"])
    run_worker()
    cmp = client.get(f"/api/v1/scans/{s2['id']}/compare/{s1['id']}", headers=h).json()  # order is normalised
    assert cmp["base_scan_id"] == s1["id"]
    assert any(i["rule_id"] == "image-alt" for i in cmp["resolved_issues"])
    assert any(i["rule_id"] == "button-name" for i in cmp["new_issues"])
    assert any(i["rule_id"] == "label" for i in cmp["remaining_issues"])
    s2 = client.get(f"/api/v1/scans/{s2['id']}", headers=h).json()
    assert s2["summary"]["vs_previous"]["resolved_violations"] >= 1
    assert client.get("/api/v1/dashboard", headers=h).json()["fixed_between_scans"] >= 1


@pytest.mark.browser
def test_crawl_scan_and_blocked_target_via_api(client: TestClient, user: dict[str, Any], site: FixtureSite) -> None:
    h = user["headers"]
    ws = add_site(client, user, f"{site.base}/index.html")
    sc = start_scan(client, user, ws["id"], mode="crawl", max_pages=3, max_depth=2)
    run_worker()
    sc = client.get(f"/api/v1/scans/{sc['id']}", headers=h).json()
    assert sc["status"] == "completed" and sc["summary"]["pages_scanned"] == 3
    assert sc["config"]["mode"] == "crawl" and sc["config"]["max_pages"] == 3


@pytest.mark.browser
def test_scan_with_only_failed_pages_is_marked_failed(
    client: TestClient, user: dict[str, Any], site: FixtureSite
) -> None:
    ws = add_site(client, user, f"{site.base}/not-found.html")
    sc = start_scan(client, user, ws["id"])
    run_worker()
    sc = client.get(f"/api/v1/scans/{sc['id']}", headers=user["headers"]).json()
    assert sc["status"] == "failed" and "404" in sc["error_message"]
    assert any(n["kind"] == "scan_failed" for n in client.get("/api/v1/notifications", headers=user["headers"]).json())
    assert (
        client.post("/api/v1/reports", headers=user["headers"], json={"scan_id": sc["id"], "format": "pdf"}).status_code
        == 400
    )


# ----------------------------------------------------------------------------- job reliability


class ExplodingEngine:
    async def run(self, *args: Any, **kw: Any) -> Any:
        raise RuntimeError("browser crashed")


def test_engine_crash_marks_scan_failed(client: TestClient, user: dict[str, Any]) -> None:
    site = add_site(client, user, "https://example.com")
    sc = start_scan(client, user, site["id"])
    asyncio.run(Worker(engine_factory=ExplodingEngine).run_once())
    sc = client.get(f"/api/v1/scans/{sc['id']}", headers=user["headers"]).json()
    assert sc["status"] == "failed" and "browser crashed" in sc["error_message"] and sc["finished_at"]


def test_stale_running_scan_is_requeued_then_failed(client: TestClient, user: dict[str, Any]) -> None:
    site = add_site(client, user, "https://example.com")
    sc = start_scan(client, user, site["id"])
    w = Worker(engine_factory=ExplodingEngine)
    with session_factory()() as db:
        db.execute(
            update(Scan)
            .where(Scan.id == uuid.UUID(sc["id"]))
            .values(status="running", attempts=1, heartbeat_at=utcnow() - timedelta(hours=2))
        )
        db.commit()
    assert w.recover_stale() == 1
    assert client.get(f"/api/v1/scans/{sc['id']}", headers=user["headers"]).json()["status"] == "queued"
    with session_factory()() as db:
        db.execute(
            update(Scan)
            .where(Scan.id == uuid.UUID(sc["id"]))
            .values(status="running", attempts=2, heartbeat_at=utcnow() - timedelta(hours=2))
        )
        db.commit()
    w.recover_stale()
    final = client.get(f"/api/v1/scans/{sc['id']}", headers=user["headers"]).json()
    assert final["status"] == "failed" and "interrupted" in final["error_message"]


def test_claim_is_atomic(client: TestClient, user: dict[str, Any]) -> None:
    site = add_site(client, user, "https://example.com")
    start_scan(client, user, site["id"])
    w1, w2 = Worker(), Worker()
    first, second = w1.claim_next(), w2.claim_next()
    assert first is not None and second is None


def test_cancel_queued_scan(client: TestClient, user: dict[str, Any]) -> None:
    site = add_site(client, user, "https://example.com")
    sc = start_scan(client, user, site["id"])
    r = client.post(f"/api/v1/scans/{sc['id']}/cancel", headers=user["headers"])
    assert r.json()["status"] == "cancelled"
    assert Worker().claim_next() is None
    assert client.post(f"/api/v1/scans/{sc['id']}/cancel", headers=user["headers"]).status_code == 409
    assert client.delete(f"/api/v1/scans/{sc['id']}", headers=user["headers"]).status_code == 204


def test_monitoring_schedules_scans(client: TestClient, user: dict[str, Any]) -> None:
    h = user["headers"]
    site = add_site(client, user, "https://example.com")
    r = client.put(
        f"/api/v1/websites/{site['id']}/monitoring",
        headers=h,
        json={"enabled": True, "frequency": "daily", "mode": "single"},
    )
    assert r.status_code == 200 and r.json()["next_run_at"]
    w = Worker()
    assert w.schedule_due() == 0  # not due yet
    with session_factory()() as db:
        db.execute(update(MonitoringConfig).values(next_run_at=utcnow() - timedelta(minutes=1)))
        db.commit()
    assert w.schedule_due() == 1
    assert w.schedule_due() == 0  # next run moved forward; active scan not duplicated
    scans = client.get(f"/api/v1/scans?website_id={site['id']}", headers=h).json()
    assert scans["total"] == 1 and scans["items"][0]["trigger"] == "schedule"
    r = client.put(f"/api/v1/websites/{site['id']}/monitoring", headers=h, json={"enabled": False})
    assert r.json()["enabled"] is False and r.json()["next_run_at"] is None
    with session_factory()() as db:
        assert db.scalar(select(MonitoringConfig.enabled)) is False
    assert len(client.get("/api/v1/monitoring", headers=h).json()) == 1


def test_contrast_endpoint(client: TestClient) -> None:
    r = client.post("/api/v1/tools/contrast", json={"foreground": "#767676", "background": "#ffffff"})
    assert r.json()["ratio"] == 4.54 and r.json()["aa_normal"] is True
    assert client.post("/api/v1/tools/contrast", json={"foreground": "blue", "background": "#fff"}).status_code == 422


def test_meta_endpoints(client: TestClient) -> None:
    assert len(client.get("/api/v1/wcag/manual-checks").json()) >= 10
    assert client.get("/api/v1/scoring/methodology").json()["weights"]["critical"] == 10
    assert any(c["number"] == "2.5.8" for c in client.get("/api/v1/wcag/criteria").json())


# ----------------------------------------------------------------------------- data isolation


@pytest.mark.browser
def test_user_data_isolation(
    client: TestClient, user: dict[str, Any], other_user: dict[str, Any], site: FixtureSite
) -> None:
    a, b = user["headers"], other_user["headers"]
    ws = add_site(client, user, f"{site.base}/violations.html")
    sc = start_scan(client, user, ws["id"])
    run_worker()
    issue = client.get(f"/api/v1/issues?scan_id={sc['id']}", headers=a).json()["items"][0]
    rep = client.post("/api/v1/reports", headers=a, json={"scan_id": sc["id"], "format": "csv"}).json()

    # B sees nothing of A's data, and every direct-ID access returns 404
    assert client.get("/api/v1/websites", headers=b).json() == []
    assert client.get("/api/v1/scans", headers=b).json()["total"] == 0
    assert client.get("/api/v1/issues", headers=b).json()["total"] == 0
    assert client.get("/api/v1/reports", headers=b).json() == []
    assert client.get("/api/v1/dashboard", headers=b).json()["total_scans"] == 0
    for method, path, body in [
        ("GET", f"/api/v1/websites/{ws['id']}", None),
        ("PATCH", f"/api/v1/websites/{ws['id']}", {"name": "pwned"}),
        ("DELETE", f"/api/v1/websites/{ws['id']}", None),
        ("GET", f"/api/v1/websites/{ws['id']}/analytics", None),
        ("PUT", f"/api/v1/websites/{ws['id']}/monitoring", {"enabled": True}),
        ("GET", f"/api/v1/scans/{sc['id']}", None),
        ("GET", f"/api/v1/scans/{sc['id']}/pages", None),
        ("POST", f"/api/v1/scans/{sc['id']}/cancel", None),
        ("DELETE", f"/api/v1/scans/{sc['id']}", None),
        ("GET", f"/api/v1/issues?scan_id={sc['id']}", None),
        ("GET", f"/api/v1/issues/{issue['id']}", None),
        ("PATCH", f"/api/v1/issues/{issue['id']}/status", {"status": "marked_fixed"}),
        ("POST", f"/api/v1/issues/{issue['id']}/notes", {"body": "x"}),
        ("POST", "/api/v1/reports", {"scan_id": sc["id"], "format": "pdf"}),
        ("GET", f"/api/v1/reports/{rep['id']}/download", None),
        ("DELETE", f"/api/v1/reports/{rep['id']}", None),
        ("POST", "/api/v1/scans", {"website_id": ws["id"]}),
        ("POST", f"/api/v1/ai/issues/{issue['id']}/remediation", None),
    ]:
        r = client.request(method, path, headers=b, json=body)
        assert r.status_code == 404, f"{method} {path} -> {r.status_code}"
    # bulk update silently ignores foreign IDs
    r = client.post(
        "/api/v1/issues/bulk-status", headers=b, json={"issue_ids": [issue["id"]], "status": "marked_fixed"}
    )
    assert r.json() == {"updated": 0}
    # B cannot compare its own scan with A's scan
    ws_b = add_site(client, other_user, "https://example.com")
    sc_b = start_scan(client, other_user, ws_b["id"])
    assert client.get(f"/api/v1/scans/{sc_b['id']}/compare/{sc['id']}", headers=b).status_code == 404
    # A's data is untouched
    assert client.get(f"/api/v1/issues/{issue['id']}", headers=a).json()["status"] == "open"
