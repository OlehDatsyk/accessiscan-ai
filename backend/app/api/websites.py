"""Website (project) management."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from app.deps import DB, CurrentUser, get_owned_website
from app.models import Issue, MonitoringConfig, Scan, Website
from app.scanner.url_safety import UnsafeURLError, validate_target
from app.schemas import WebsiteIn, WebsiteOut, WebsiteUpdate
from app.services import log_activity

router = APIRouter(prefix="/websites", tags=["websites"])


def validated_url(raw: str) -> str:
    try:
        return validate_target(raw).url
    except UnsafeURLError as exc:
        raise HTTPException(422, str(exc)) from None


def website_out(db: DB, site: Website) -> WebsiteOut:
    out = WebsiteOut.model_validate(site)
    latest = db.scalar(select(Scan).where(Scan.website_id == site.id).order_by(Scan.created_at.desc()).limit(1))
    latest_done = db.scalar(
        select(Scan)
        .where(Scan.website_id == site.id, Scan.status == "completed")
        .order_by(Scan.created_at.desc())
        .limit(1)
    )
    out.scan_count = int(db.scalar(select(func.count()).select_from(Scan).where(Scan.website_id == site.id)) or 0)
    if latest is not None:
        out.latest_scan_id, out.latest_scan_at, out.latest_scan_status = latest.id, latest.created_at, latest.status
    if latest_done is not None:
        out.latest_score = latest_done.score
        out.open_violations = int(
            db.scalar(
                select(func.count())
                .select_from(Issue)
                .where(
                    Issue.scan_id == latest_done.id,
                    Issue.kind == "violation",
                    Issue.status.in_(("open", "in_progress")),
                )
            )
            or 0
        )
    mon = db.scalar(select(MonitoringConfig).where(MonitoringConfig.website_id == site.id))
    out.monitoring_enabled = bool(mon and mon.enabled)
    return out


@router.get("", response_model=list[WebsiteOut])
def list_websites(user: CurrentUser, db: DB, include_archived: bool = Query(False)) -> list[WebsiteOut]:
    q = select(Website).where(Website.owner_id == user.id)
    if not include_archived:
        q = q.where(Website.is_archived.is_(False))
    return [website_out(db, s) for s in db.scalars(q.order_by(Website.created_at.desc()))]


@router.post("", response_model=WebsiteOut, status_code=status.HTTP_201_CREATED)
def create_website(body: WebsiteIn, user: CurrentUser, db: DB) -> WebsiteOut:
    count = db.scalar(select(func.count()).select_from(Website).where(Website.owner_id == user.id)) or 0
    if count >= 100:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Website limit reached (100)")
    site = Website(
        owner_id=user.id, name=body.name.strip(), url=validated_url(body.url), description=body.description.strip()
    )
    db.add(site)
    db.flush()
    log_activity(db, user.id, "website.created", "website", site.id, site.url)
    db.commit()
    return website_out(db, site)


@router.get("/{website_id}", response_model=WebsiteOut)
def get_website(website_id: uuid.UUID, user: CurrentUser, db: DB) -> WebsiteOut:
    return website_out(db, get_owned_website(db, user, website_id))


@router.patch("/{website_id}", response_model=WebsiteOut)
def update_website(website_id: uuid.UUID, body: WebsiteUpdate, user: CurrentUser, db: DB) -> WebsiteOut:
    site = get_owned_website(db, user, website_id)
    data = body.model_dump(exclude_none=True)
    if "url" in data:
        data["url"] = validated_url(data["url"])
    for k, v in data.items():
        setattr(site, k, v.strip() if isinstance(v, str) else v)
    if data.get("is_archived") and site.monitoring is not None:
        site.monitoring.enabled = False
    log_activity(db, user.id, "website.updated", "website", site.id, ", ".join(data))
    db.commit()
    return website_out(db, site)


@router.delete("/{website_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_website(website_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    site = get_owned_website(db, user, website_id)
    if db.scalar(select(Scan.id).where(Scan.website_id == site.id, Scan.status == "running").limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Wait for the running scan to finish (or cancel it) first")
    log_activity(db, user.id, "website.deleted", "website", site.id, site.url)
    db.delete(site)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{website_id}/analytics")
def website_analytics(website_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    site = get_owned_website(db, user, website_id)
    scans = list(
        db.scalars(select(Scan).where(Scan.website_id == site.id, Scan.status == "completed").order_by(Scan.created_at))
    )
    trend = []
    for s in scans[-50:]:
        summ = s.summary or {}
        vs = summ.get("vs_previous") or {}
        trend.append(
            {
                "scan_id": str(s.id),
                "date": s.created_at.isoformat(),
                "score": s.score,
                "violations": summ.get("violations", 0),
                "needs_review": summ.get("needs_review", 0),
                **{k: summ.get("by_impact", {}).get(k, 0) for k in ("critical", "serious", "moderate", "minor")},
                "new": vs.get("new_violations"),
                "resolved": vs.get("resolved_violations"),
            }
        )
    latest = scans[-1] if scans else None
    return {"trend": trend, "latest_summary": latest.summary if latest else None}
