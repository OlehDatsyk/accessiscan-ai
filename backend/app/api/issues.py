"""Issue listing, filtering and management (status, notes, history)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app import guidance, wcag
from app.deps import DB, CurrentUser, get_owned_issue, get_owned_scan
from app.models import AISuggestion, Issue, IssueNote, IssueStatusHistory, Scan, User, Website
from app.schemas import BulkStatusIn, IssueDetail, IssueOut, IssueStatusIn, NoteIn, NoteOut, Page
from app.services import log_activity

router = APIRouter(prefix="/issues", tags=["issues"])

SEVERITY_SORT = case({"critical": 0, "serious": 1, "moderate": 2, "minor": 3}, value=Issue.impact, else_=4)


def latest_scan_ids(db: Session, user: User) -> list[uuid.UUID]:
    ids = []
    for site_id in db.scalars(select(Website.id).where(Website.owner_id == user.id, Website.is_archived.is_(False))):
        sid = db.scalar(
            select(Scan.id)
            .where(Scan.website_id == site_id, Scan.status == "completed")
            .order_by(Scan.created_at.desc())
            .limit(1)
        )
        if sid:
            ids.append(sid)
    return ids


def _filtered(
    db: Session,
    user: User,
    *,
    scan_id: uuid.UUID | None,
    website_id: uuid.UUID | None,
    impact: list[str] | None,
    kind: str | None,
    category: str | None,
    wcag_criterion: str | None,
    status_filter: list[str] | None,
    q: str | None,
    latest_only: bool,
    level: str | None,
    best_practice: bool | None,
) -> Any:
    query = select(Issue).where(Issue.owner_id == user.id)
    if scan_id:
        get_owned_scan(db, user, scan_id)
        query = query.where(Issue.scan_id == scan_id)
    elif latest_only:
        query = query.where(Issue.scan_id.in_(latest_scan_ids(db, user)))
    if website_id:
        query = query.where(Issue.website_id == website_id)
    if impact:
        query = query.where(Issue.impact.in_(impact))
    if kind:
        query = query.where(Issue.kind == kind)
    if category:
        query = query.where(Issue.category == category)
    if level:
        query = query.where(Issue.wcag_level == level)
    if best_practice is not None:
        query = query.where(Issue.is_best_practice.is_(best_practice))
    if status_filter:
        query = query.where(Issue.status.in_(status_filter))
    if wcag_criterion:
        # The JSON list is stored as text on PostgreSQL and SQLite. The value is validated as "1.4.3"-style
        # by the endpoint, so it cannot contain LIKE wildcards.
        query = query.where(cast(Issue.wcag_criteria, String).like(f'%"{wcag_criterion}"%'))
    if q:
        like = f"%{q.strip()[:100].lower()}%"
        query = query.where(
            or_(
                func.lower(Issue.rule_id).like(like),
                func.lower(Issue.help).like(like),
                func.lower(Issue.selector).like(like),
                func.lower(Issue.page_url).like(like),
                func.lower(Issue.description).like(like),
            )
        )
    return query


@router.get("", response_model=Page[IssueOut])
def list_issues(
    user: CurrentUser,
    db: DB,
    scan_id: uuid.UUID | None = None,
    website_id: uuid.UUID | None = None,
    impact: list[str] | None = Query(None),
    kind: str | None = Query(None, pattern="^(violation|needs_review)$"),
    category: str | None = None,
    wcag_criterion: str | None = Query(None, alias="wcag", pattern=r"^\d\.\d\.\d{1,2}$"),
    level: str | None = Query(None, pattern="^(A|AA|AAA)$"),
    best_practice: bool | None = None,
    status_filter: list[str] | None = Query(None, alias="status"),
    q: str | None = Query(None, max_length=100),
    latest_only: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> Page[IssueOut]:
    query = _filtered(
        db,
        user,
        scan_id=scan_id,
        website_id=website_id,
        impact=impact,
        kind=kind,
        category=category,
        wcag_criterion=wcag_criterion,
        status_filter=status_filter,
        q=q,
        latest_only=latest_only,
        level=level,
        best_practice=best_practice,
    )
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = db.scalars(
        query.order_by(Issue.kind.desc(), SEVERITY_SORT, Issue.rule_id, Issue.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page[IssueOut](
        items=[IssueOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/facets")
def facets(
    user: CurrentUser,
    db: DB,
    scan_id: uuid.UUID | None = None,
    website_id: uuid.UUID | None = None,
    latest_only: bool = True,
) -> dict[str, Any]:
    query = _filtered(
        db,
        user,
        scan_id=scan_id,
        website_id=website_id,
        impact=None,
        kind=None,
        category=None,
        wcag_criterion=None,
        status_filter=None,
        q=None,
        latest_only=latest_only,
        level=None,
        best_practice=None,
    )
    rows = db.scalars(query).all()
    out: dict[str, dict[str, int]] = {"impact": {}, "category": {}, "wcag": {}, "status": {}, "kind": {}}
    for r in rows:
        out["kind"][r.kind] = out["kind"].get(r.kind, 0) + 1
        out["status"][r.status] = out["status"].get(r.status, 0) + 1
        out["impact"][r.impact] = out["impact"].get(r.impact, 0) + 1
        out["category"][r.category] = out["category"].get(r.category, 0) + 1
        for c in r.wcag_criteria or []:
            out["wcag"][c] = out["wcag"].get(c, 0) + 1
    out["wcag"] = dict(sorted(out["wcag"].items(), key=lambda kv: [int(x) for x in kv[0].split(".")]))
    return {**out, "category_labels": wcag.CATEGORY_LABELS}


@router.get("/{issue_id}", response_model=IssueDetail)
def get_issue(issue_id: uuid.UUID, user: CurrentUser, db: DB) -> IssueDetail:
    issue = get_owned_issue(db, user, issue_id)
    out = IssueDetail.model_validate(issue)
    out.wcag_details = [wcag.describe(c) for c in issue.wcag_criteria or []]
    out.guidance = guidance.for_rule(issue.rule_id)
    sug = db.scalar(
        select(AISuggestion)
        .where(AISuggestion.issue_id == issue.id, AISuggestion.owner_id == user.id)
        .order_by(AISuggestion.created_at.desc())
        .limit(1)
    )
    if sug is not None:
        out.ai_suggestion = {
            **sug.content,
            "provider": sug.provider,
            "model": sug.model,
            "created_at": sug.created_at.isoformat(),
        }
    return out


def _set_status(db: Session, user: User, issue: Issue, body: IssueStatusIn) -> None:
    if body.status == "ignored" and not body.reason.strip():
        raise HTTPException(422, "A reason is required when ignoring an issue")
    if issue.status == body.status and issue.status_reason == body.reason.strip():
        return
    db.add(
        IssueStatusHistory(
            issue_id=issue.id,
            actor_id=user.id,
            from_status=issue.status,
            to_status=body.status,
            reason=body.reason.strip(),
        )
    )
    issue.status, issue.status_reason = body.status, body.reason.strip()


@router.patch("/{issue_id}/status", response_model=IssueDetail)
def update_status(issue_id: uuid.UUID, body: IssueStatusIn, user: CurrentUser, db: DB) -> IssueDetail:
    issue = get_owned_issue(db, user, issue_id)
    _set_status(db, user, issue, body)
    log_activity(db, user.id, "issue.status", "issue", issue.id, body.status)
    db.commit()
    db.refresh(issue)
    return get_issue(issue_id, user, db)


@router.post("/bulk-status")
def bulk_status(body: BulkStatusIn, user: CurrentUser, db: DB) -> dict[str, int]:
    issues = list(db.scalars(select(Issue).where(Issue.id.in_(body.issue_ids), Issue.owner_id == user.id)))
    for issue in issues:
        _set_status(db, user, issue, body)
    log_activity(db, user.id, "issue.bulk_status", "issue", "", f"{len(issues)} -> {body.status}")
    db.commit()
    return {"updated": len(issues)}


@router.post("/{issue_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def add_note(issue_id: uuid.UUID, body: NoteIn, user: CurrentUser, db: DB) -> IssueNote:
    issue = get_owned_issue(db, user, issue_id)
    note = IssueNote(issue_id=issue.id, author_id=user.id, body=body.body.strip())
    db.add(note)
    log_activity(db, user.id, "issue.note", "issue", issue.id)
    db.commit()
    return note
