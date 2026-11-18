"""Report generation and download (PDF, CSV, DOCX). Files are stored in the database (persistent,
access-controlled), never on the public filesystem."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import defer

from app import reports
from app.config import get_settings
from app.deps import DB, CurrentUser, get_owned_scan, not_found
from app.models import AISuggestion, Issue, Report, ScanPage
from app.schemas import ReportCreate, ReportOut
from app.services import log_activity

router = APIRouter(prefix="/reports", tags=["reports"])
MEDIA = {
    "pdf": "application/pdf",
    "csv": "text/csv; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("", response_model=list[ReportOut])
def list_reports(user: CurrentUser, db: DB, scan_id: uuid.UUID | None = None) -> list[Report]:
    q = select(Report).options(defer(Report.content)).where(Report.owner_id == user.id)
    if scan_id:
        q = q.where(Report.scan_id == scan_id)
    return list(db.scalars(q.order_by(Report.created_at.desc()).limit(200)))


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
def create_report(body: ReportCreate, user: CurrentUser, db: DB) -> Report:
    scan = get_owned_scan(db, user, body.scan_id)
    if scan.status not in ("completed", "cancelled"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Reports can be generated for completed scans only")
    site = scan.website
    issues = list(
        db.scalars(
            select(Issue)
            .where(Issue.scan_id == scan.id, Issue.owner_id == user.id)
            .limit(get_settings().report_max_issues)
        )
    )
    pages = list(db.scalars(select(ScanPage).where(ScanPage.scan_id == scan.id).order_by(ScanPage.scanned_at)))
    if body.format == "csv":
        content = reports.build_csv(scan, site, issues)
    elif body.format == "docx":
        content = reports.build_docx(scan, site, issues, pages)
    else:
        sugg = {
            str(s.issue_id): s.content
            for s in db.scalars(
                select(AISuggestion).where(
                    AISuggestion.owner_id == user.id, AISuggestion.issue_id.in_([i.id for i in issues])
                )
            )
        }
        content = reports.build_pdf(scan, site, issues, pages, sugg)
    slug = re.sub(r"[^a-z0-9]+", "-", site.name.lower()).strip("-")[:40] or "website"
    filename = f"accessiscan-{slug}-{scan.created_at:%Y%m%d-%H%M}.{body.format}"
    report = Report(
        owner_id=user.id,
        scan_id=scan.id,
        format=body.format,
        filename=filename,
        size_bytes=len(content),
        content=content,
    )
    db.add(report)
    log_activity(db, user.id, "report.created", "scan", scan.id, body.format)
    db.commit()
    return report


@router.get("/{report_id}/download")
def download(report_id: uuid.UUID, user: CurrentUser, db: DB, inline: bool = Query(False)) -> Response:
    report = db.scalar(select(Report).where(Report.id == report_id, Report.owner_id == user.id))
    if report is None:
        raise not_found("Report")
    disp = "inline" if inline and report.format == "pdf" else "attachment"
    return Response(
        content=report.content,
        media_type=MEDIA[report.format],
        headers={
            "Content-Disposition": f'{disp}; filename="{report.filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(report_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    report = db.scalar(select(Report).where(Report.id == report_id, Report.owner_id == user.id))
    if report is None:
        raise not_found("Report")
    db.delete(report)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
