"""Scan creation, status, pages, comparison and cancellation."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from app import scoring, wcag
from app.config import get_settings
from app.db import utcnow
from app.deps import DB, CurrentUser, get_owned_scan, get_owned_website
from app.models import Scan, ScanComparison, ScanPage, Website
from app.scanner.url_safety import UnsafeURLError, validate_target
from app.schemas import Page, ScanCreate, ScanOut, ScanPageOut
from app.services import compare_scans, count_active_scans, log_activity

router = APIRouter(prefix="/scans", tags=["scans"])
meta_router = APIRouter(tags=["meta"])


def _bare_host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def scan_out(scan: Scan, site: Website | None = None) -> ScanOut:
    out = ScanOut.model_validate(scan)
    site = site or scan.website
    if site is not None:
        out.website_name, out.website_url = site.name, site.url
    return out


@router.post("", response_model=ScanOut, status_code=status.HTTP_202_ACCEPTED)
def create_scan(body: ScanCreate, user: CurrentUser, db: DB) -> ScanOut:
    s = get_settings()
    site = get_owned_website(db, user, body.website_id)
    if site.is_archived:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Restore the archived website before scanning it")
    if count_active_scans(db, user.id) >= s.scan_user_max_active:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You already have {s.scan_user_max_active} scans queued or running. Wait for them to finish",
        )
    recent = (
        db.scalar(
            select(func.count())
            .select_from(Scan)
            .where(Scan.owner_id == user.id, Scan.trigger == "manual", Scan.created_at >= utcnow() - timedelta(hours=1))
        )
        or 0
    )
    if recent >= s.scan_user_hourly_limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Scan limit reached ({s.scan_user_hourly_limit} per hour). Try again later",
        )

    raw_urls = [u for u in (body.urls or []) if u.strip()] or [site.url]
    if body.mode != "list":
        raw_urls = raw_urls[:1]
    max_pages = min(body.max_pages, s.scan_max_pages)
    if body.mode == "single":
        max_pages = 1
    elif body.mode == "list":
        if len(raw_urls) > max_pages:
            raise HTTPException(422, f"At most {max_pages} URLs can be scanned in one list scan")
        max_pages = len(raw_urls)

    site_host = _bare_host(site.url)
    urls: list[str] = []
    for raw in raw_urls:
        try:
            safe = validate_target(raw)
        except UnsafeURLError as exc:
            raise HTTPException(422, f"{raw[:200]}: {exc}") from None
        if _bare_host(safe.url) != site_host:
            raise HTTPException(
                422,
                f"{raw[:200]}: URLs must belong to the website's domain ({site_host})",
            )
        if safe.url not in urls:
            urls.append(safe.url)

    config = {
        "urls": urls,
        "mode": body.mode,
        "max_pages": max_pages,
        "max_depth": min(body.max_depth, s.scan_max_depth) if body.mode == "crawl" else 0,
        "include_aaa": body.include_aaa,
        "respect_robots": body.respect_robots,
        "limits": {
            "timeout_seconds": s.scan_timeout_seconds,
            "page_timeout_seconds": s.scan_page_timeout_seconds,
            "max_page_mb": s.scan_max_page_mb,
            "max_total_mb": s.scan_max_total_mb,
            "crawl_delay_ms": s.scan_crawl_delay_ms,
        },
    }
    scan = Scan(
        owner_id=user.id,
        website_id=site.id,
        mode=body.mode,
        trigger="manual",
        config=config,
        pages_total=max_pages,
        progress_message="Queued",
    )
    db.add(scan)
    db.flush()
    log_activity(db, user.id, "scan.created", "scan", scan.id, f"{body.mode} {urls[0]}")
    db.commit()
    return scan_out(scan, site)


@router.get("", response_model=Page[ScanOut])
def list_scans(
    user: CurrentUser,
    db: DB,
    website_id: uuid.UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[ScanOut]:
    q = select(Scan).where(Scan.owner_id == user.id)
    if website_id:
        q = q.where(Scan.website_id == website_id)
    if status_filter:
        q = q.where(Scan.status == status_filter)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(Scan.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return Page[ScanOut](items=[scan_out(r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: uuid.UUID, user: CurrentUser, db: DB) -> ScanOut:
    return scan_out(get_owned_scan(db, user, scan_id))


@router.post("/{scan_id}/cancel", response_model=ScanOut)
def cancel_scan(scan_id: uuid.UUID, user: CurrentUser, db: DB) -> ScanOut:
    scan = get_owned_scan(db, user, scan_id)
    if scan.status == "queued":
        scan.status, scan.finished_at, scan.cancel_requested = "cancelled", utcnow(), True
    elif scan.status == "running":
        scan.cancel_requested = True
        scan.progress_message = "Cancelling..."
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only queued or running scans can be cancelled")
    log_activity(db, user.id, "scan.cancelled", "scan", scan.id)
    db.commit()
    return scan_out(scan)


@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scan(scan_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    scan = get_owned_scan(db, user, scan_id)
    if scan.status in ("queued", "running"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cancel the scan before deleting it")
    log_activity(db, user.id, "scan.deleted", "scan", scan.id)
    db.delete(scan)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{scan_id}/pages", response_model=list[ScanPageOut])
def scan_pages(scan_id: uuid.UUID, user: CurrentUser, db: DB) -> list[ScanPage]:
    scan = get_owned_scan(db, user, scan_id)
    return list(db.scalars(select(ScanPage).where(ScanPage.scan_id == scan.id).order_by(ScanPage.scanned_at)))


@router.get("/{scan_id}/compare/{other_id}")
def compare(scan_id: uuid.UUID, other_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    """Compare ``scan_id`` (base, older) with ``other_id`` (target, newer)."""
    base = get_owned_scan(db, user, scan_id)
    target = get_owned_scan(db, user, other_id)
    if base.website_id != target.website_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only scans of the same website can be compared")
    if base.status != "completed" or target.status != "completed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Both scans must be completed")
    if base.created_at > target.created_at:
        base, target = target, base
    result = compare_scans(db, base, target)
    db.add(
        ScanComparison(
            owner_id=user.id,
            website_id=base.website_id,
            base_scan_id=base.id,
            target_scan_id=target.id,
            summary={k: v for k, v in result.items() if not k.endswith("_issues")},
        )
    )
    db.commit()
    return result


@meta_router.get("/scoring/methodology", tags=["meta"])
def methodology() -> dict[str, Any]:
    return scoring.methodology()


@meta_router.get("/wcag/manual-checks", tags=["meta"])
def manual_checks() -> list[dict[str, Any]]:
    return [
        {**m, **{"name": wcag.describe(m["criterion"])["name"], "level": wcag.describe(m["criterion"])["level"]}}
        for m in wcag.MANUAL_REVIEW_CHECKS
    ]


@meta_router.get("/wcag/criteria", tags=["meta"])
def criteria() -> list[dict[str, Any]]:
    return [wcag.describe(n) for n in wcag.CRITERIA]
