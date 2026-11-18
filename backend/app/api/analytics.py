"""Dashboard, analytics, monitoring, notifications and tools. All numbers come from stored records."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select, update

from app import contrast, wcag
from app.db import utcnow
from app.deps import DB, CurrentUser, get_owned_website, not_found
from app.models import ActivityLog, Issue, MonitoringConfig, Notification, Scan, Website
from app.schemas import ContrastIn, MonitoringIn, MonitoringOut, NotificationOut, ScanOut
from app.services import log_activity
from app.worker import next_run

router = APIRouter(tags=["analytics"])


def _latest_completed(db: DB, site_id: uuid.UUID, n: int = 1) -> list[Scan]:
    return list(
        db.scalars(
            select(Scan)
            .where(Scan.website_id == site_id, Scan.status == "completed")
            .order_by(Scan.created_at.desc())
            .limit(n)
        )
    )


@router.get("/dashboard")
def dashboard(user: CurrentUser, db: DB) -> dict[str, Any]:
    sites = list(db.scalars(select(Website).where(Website.owner_id == user.id, Website.is_archived.is_(False))))
    total_scans = db.scalar(select(func.count()).select_from(Scan).where(Scan.owner_id == user.id)) or 0
    by_impact: Counter[str] = Counter()
    needs_review = 0
    fixed_between = 0
    scores: list[float] = []
    attention = []
    for site in sites:
        latest = _latest_completed(db, site.id, 2)
        if not latest:
            continue
        s = latest[0].summary or {}
        for k, v in (s.get("by_impact") or {}).items():
            by_impact[k] += v
        needs_review += s.get("needs_review", 0)
        if latest[0].score is not None:
            scores.append(latest[0].score)
        vs = s.get("vs_previous") or {}
        fixed_between += int(vs.get("resolved_violations") or 0)
        crit = (s.get("by_impact") or {}).get("critical", 0)
        if (latest[0].score is not None and latest[0].score < 70) or crit > 0 or vs.get("new_violations"):
            attention.append(
                {
                    "website_id": str(site.id),
                    "name": site.name,
                    "url": site.url,
                    "score": latest[0].score,
                    "critical": crit,
                    "new_violations": vs.get("new_violations") or 0,
                    "scan_id": str(latest[0].id),
                }
            )
    recent = list(db.scalars(select(Scan).where(Scan.owner_id == user.id).order_by(Scan.created_at.desc()).limit(8)))
    activity_rows = db.execute(
        select(func.date(Scan.created_at), func.count())
        .where(Scan.owner_id == user.id, Scan.created_at >= utcnow() - timedelta(days=30))
        .group_by(func.date(Scan.created_at))
        .order_by(func.date(Scan.created_at))
    ).all()
    from app.models import Report

    latest_reports = db.execute(
        select(Report.id, Report.filename, Report.format, Report.created_at, Report.scan_id)
        .where(Report.owner_id == user.id)
        .order_by(Report.created_at.desc())
        .limit(5)
    ).all()
    return {
        "websites": len(sites),
        "total_scans": total_scans,
        "issues_detected": sum(by_impact.values()),
        "critical_issues": by_impact.get("critical", 0),
        "by_impact": {k: by_impact.get(k, 0) for k in ("critical", "serious", "moderate", "minor")},
        "needs_review": needs_review,
        "fixed_between_scans": fixed_between,
        "average_score": round(sum(scores) / len(scores), 1) if scores else None,
        "scored_websites": len(scores),
        "recent_scans": [_scan_brief(s) for s in recent],
        "attention": sorted(attention, key=lambda a: (-(a["critical"] or 0), a["score"] or 0))[:6],
        "scan_activity": [{"date": str(d), "scans": c} for d, c in activity_rows],
        "latest_reports": [
            {
                "id": str(r.id),
                "filename": r.filename,
                "format": r.format,
                "created_at": r.created_at.isoformat(),
                "scan_id": str(r.scan_id),
            }
            for r in latest_reports
        ],
    }


def _scan_brief(s: Scan) -> dict[str, Any]:
    out = ScanOut.model_validate(s).model_dump(
        mode="json", include={"id", "status", "score", "created_at", "mode", "trigger", "website_id", "pages_done"}
    )
    out["website_name"] = s.website.name if s.website else ""
    out["violations"] = (s.summary or {}).get("violations")
    return out


@router.get("/analytics")
def analytics(user: CurrentUser, db: DB) -> dict[str, Any]:
    sites = list(db.scalars(select(Website).where(Website.owner_id == user.id, Website.is_archived.is_(False))))
    by_impact: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    ranges = {"90-100": 0, "70-89": 0, "50-69": 0, "0-49": 0}
    latest_ids = []
    for site in sites:
        latest = _latest_completed(db, site.id)
        if not latest:
            continue
        latest_ids.append(latest[0].id)
        s = latest[0].summary or {}
        by_impact.update(s.get("by_impact") or {})
        by_category.update(s.get("by_category") or {})
        sc = latest[0].score
        if sc is not None:
            ranges["90-100" if sc >= 90 else "70-89" if sc >= 70 else "50-69" if sc >= 50 else "0-49"] += 1
    completed = list(
        db.scalars(
            select(Scan)
            .where(Scan.owner_id == user.id, Scan.status == "completed")
            .order_by(Scan.created_at)
            .limit(500)
        )
    )
    score_trend = [
        {"date": s.created_at.isoformat(), "score": s.score, "website": s.website.name, "website_id": str(s.website_id)}
        for s in completed
    ]
    new_vs_resolved = []
    for s in completed[-30:]:
        vs = (s.summary or {}).get("vs_previous")
        if vs:
            new_vs_resolved.append(
                {
                    "date": s.created_at.isoformat(),
                    "website": s.website.name,
                    "new": vs.get("new_violations", 0),
                    "resolved": vs.get("resolved_violations", 0),
                }
            )
    status_counts = (
        dict(
            db.execute(
                select(Issue.status, func.count())
                .where(Issue.owner_id == user.id, Issue.scan_id.in_(latest_ids))
                .group_by(Issue.status)
            ).all()
        )
        if latest_ids
        else {}
    )
    activity = db.execute(
        select(func.date(Scan.created_at), func.count())
        .where(Scan.owner_id == user.id, Scan.created_at >= utcnow() - timedelta(days=90))
        .group_by(func.date(Scan.created_at))
        .order_by(func.date(Scan.created_at))
    ).all()
    return {
        "by_impact": {k: by_impact.get(k, 0) for k in ("critical", "serious", "moderate", "minor")},
        "by_category": [
            {"category": k, "label": wcag.CATEGORY_LABELS.get(k, k), "count": v} for k, v in by_category.most_common()
        ],
        "score_ranges": [{"range": k, "websites": v} for k, v in ranges.items()],
        "score_trend": score_trend,
        "new_vs_resolved": new_vs_resolved,
        "issue_status": status_counts,
        "scan_activity": [{"date": str(d), "scans": c} for d, c in activity],
    }


@router.get("/activity")
def activity(user: CurrentUser, db: DB, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(ActivityLog)
        .where(ActivityLog.owner_id == user.id)
        .order_by(ActivityLog.created_at.desc())
        .limit(min(limit, 200))
    )
    return [
        {
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "detail": r.detail,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


# ----------------------------------------------------------------------------- contrast tool
@router.post("/tools/contrast")
def contrast_check(body: ContrastIn) -> dict[str, Any]:
    try:
        result = contrast.evaluate(body.foreground, body.background)
    except contrast.ColorError as exc:
        raise HTTPException(422, str(exc)) from None
    result.pop("ratio_exact", None)
    return result


# ----------------------------------------------------------------------------- monitoring
def _mon_out(cfg: MonitoringConfig) -> MonitoringOut:
    out = MonitoringOut.model_validate(cfg)
    out.website_name, out.website_url = cfg.website.name, cfg.website.url
    return out


@router.get("/monitoring", response_model=list[MonitoringOut])
def list_monitoring(user: CurrentUser, db: DB) -> list[MonitoringOut]:
    return [_mon_out(c) for c in db.scalars(select(MonitoringConfig).where(MonitoringConfig.owner_id == user.id))]


@router.get("/websites/{website_id}/monitoring", response_model=MonitoringOut | None)
def get_monitoring(website_id: uuid.UUID, user: CurrentUser, db: DB) -> MonitoringOut | None:
    site = get_owned_website(db, user, website_id)
    cfg = db.scalar(select(MonitoringConfig).where(MonitoringConfig.website_id == site.id))
    return _mon_out(cfg) if cfg else None


@router.put("/websites/{website_id}/monitoring", response_model=MonitoringOut)
def set_monitoring(website_id: uuid.UUID, body: MonitoringIn, user: CurrentUser, db: DB) -> MonitoringOut:
    site = get_owned_website(db, user, website_id)
    if body.enabled and site.is_archived:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Archived websites cannot be monitored")
    cfg = db.scalar(select(MonitoringConfig).where(MonitoringConfig.website_id == site.id))
    if cfg is None:
        cfg = MonitoringConfig(owner_id=user.id, website_id=site.id)
        db.add(cfg)
    was_enabled = cfg.enabled
    cfg.enabled, cfg.frequency = body.enabled, body.frequency
    cfg.scan_config = {
        "mode": body.mode,
        "max_pages": body.max_pages if body.mode == "crawl" else 1,
        "max_depth": body.max_depth if body.mode == "crawl" else 0,
    }
    cfg.notify_on_complete, cfg.notify_on_regression = body.notify_on_complete, body.notify_on_regression
    if body.enabled and (not was_enabled or cfg.next_run_at is None):
        cfg.next_run_at = next_run(body.frequency)
    if not body.enabled:
        cfg.next_run_at = None
    log_activity(db, user.id, "monitoring.updated", "website", site.id, f"{body.enabled} {body.frequency}")
    db.commit()
    db.refresh(cfg)
    return _mon_out(cfg)


# ----------------------------------------------------------------------------- notifications
@router.get("/notifications", response_model=list[NotificationOut])
def notifications(user: CurrentUser, db: DB, unread_only: bool = False) -> list[Notification]:
    q = select(Notification).where(Notification.owner_id == user.id)
    if unread_only:
        q = q.where(Notification.is_read.is_(False))
    return list(db.scalars(q.order_by(Notification.created_at.desc()).limit(50)))


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(notification_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    n = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.owner_id == user.id))
    if n is None:
        raise not_found("Notification")
    n.is_read = True
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(user: CurrentUser, db: DB) -> Response:
    db.execute(update(Notification).where(Notification.owner_id == user.id).values(is_read=True))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
