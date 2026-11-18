"""AI assistant and remediation endpoints. All return 503 when AI is not configured."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import ai
from app.config import get_settings
from app.db import utcnow
from app.deps import DB, CurrentUser, get_owned_issue, get_owned_scan
from app.models import AIRequestLog, AISuggestion, Issue, User
from app.schemas import AskIn

router = APIRouter(prefix="/ai", tags=["ai"])

SEV = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}


@router.get("/status")
def ai_status(user: CurrentUser, db: DB) -> dict[str, Any]:
    used = _used_today(db, user)
    return {**ai.status(), "used_today": used}


def _used_today(db: Session, user: User) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(AIRequestLog)
            .where(AIRequestLog.owner_id == user.id, AIRequestLog.created_at >= utcnow() - timedelta(days=1))
        )
        or 0
    )


def _guard(db: Session, user: User) -> None:
    s = get_settings()
    if not s.ai_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, ai.status()["message"])
    if _used_today(db, user) >= s.ai_daily_request_limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Daily AI request limit reached ({s.ai_daily_request_limit}). Try again tomorrow",
        )


def _log(db: Session, user: User, purpose: str, result: ai.AIResult | None, ok: bool) -> None:
    s = get_settings()
    db.add(
        AIRequestLog(
            owner_id=user.id,
            provider=result.provider if result else s.ai_provider,
            model=result.model if result else s.effective_ai_model,
            purpose=purpose,
            success=ok,
            input_tokens=result.input_tokens if result else None,
            output_tokens=result.output_tokens if result else None,
        )
    )
    db.commit()


async def _run(db: Session, user: User, purpose: str, coro: Any) -> ai.AIResult:
    try:
        result: ai.AIResult = await coro
    except ai.AIUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
    except ai.AIResponseError as exc:
        _log(db, user, purpose, None, False)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    _log(db, user, purpose, result, True)
    return result


@router.post("/issues/{issue_id}/remediation")
async def remediation(issue_id: uuid.UUID, user: CurrentUser, db: DB, refresh: bool = False) -> dict[str, Any]:
    issue = get_owned_issue(db, user, issue_id)
    if not refresh:
        cached = db.scalar(
            select(AISuggestion)
            .where(AISuggestion.issue_id == issue.id, AISuggestion.owner_id == user.id)
            .order_by(AISuggestion.created_at.desc())
            .limit(1)
        )
        if cached is not None:
            return {
                **cached.content,
                "provider": cached.provider,
                "model": cached.model,
                "cached": True,
                "label": "AI-generated suggestion - review and test before applying",
            }
    _guard(db, user)
    result = await _run(db, user, "remediation", ai.remediation_for_issue(issue))
    db.add(
        AISuggestion(
            issue_id=issue.id, owner_id=user.id, provider=result.provider, model=result.model, content=result.data
        )
    )
    db.commit()
    return {
        **result.data,
        "provider": result.provider,
        "model": result.model,
        "cached": False,
        "label": "AI-generated suggestion - review and test before applying",
    }


def _overview(scan: Any) -> dict[str, Any]:
    s = scan.summary or {}
    return {
        "website": scan.website.url if scan.website else "",
        "score": scan.score,
        "pages_scanned": s.get("pages_scanned"),
        "violations_by_impact": s.get("by_impact"),
        "needs_review": s.get("needs_review"),
        "scan_date": scan.created_at.isoformat(),
    }


@router.post("/ask")
async def ask(body: AskIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    scan = get_owned_scan(db, user, body.scan_id)
    if body.issue_ids:
        issues = list(
            db.scalars(
                select(Issue).where(Issue.id.in_(body.issue_ids), Issue.owner_id == user.id, Issue.scan_id == scan.id)
            )
        )
        if not issues:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Issue not found")
    else:
        # Most severe violations of this scan (one example per rule) as context.
        all_issues = list(db.scalars(select(Issue).where(Issue.scan_id == scan.id, Issue.owner_id == user.id)))
        by_rule: dict[str, Issue] = {}
        for i in sorted(all_issues, key=lambda i: (i.kind != "violation", SEV.get(i.impact, 9))):
            by_rule.setdefault(i.rule_id, i)
        issues = list(by_rule.values())[:15]
    _guard(db, user)
    result = await _run(db, user, "assistant", ai.answer_question(body.question, issues, _overview(scan)))
    return {
        **result.data,
        "provider": result.provider,
        "model": result.model,
        "context_issue_ids": [str(i.id) for i in issues],
        "label": "AI-generated answer - verify before relying on it",
    }


@router.post("/scans/{scan_id}/summary")
async def summary(scan_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    scan = get_owned_scan(db, user, scan_id)
    if scan.status != "completed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The scan has not completed")
    groups: dict[str, dict[str, Any]] = {}
    for i in db.scalars(select(Issue).where(Issue.scan_id == scan.id, Issue.kind == "violation")):
        g = groups.setdefault(
            i.rule_id,
            {
                "rule_id": i.rule_id,
                "impact": i.impact,
                "help": i.help[:200],
                "wcag_criteria": i.wcag_criteria,
                "elements": 0,
            },
        )
        g["elements"] += 1
    rule_groups = sorted(groups.values(), key=lambda g: (SEV.get(g["impact"], 9), -g["elements"]))[:30]
    if not rule_groups:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This scan has no violations to summarise")
    _guard(db, user)
    result = await _run(db, user, "summary", ai.summarise_scan(_overview(scan), rule_groups))
    return {
        **result.data,
        "provider": result.provider,
        "model": result.model,
        "label": "AI-generated summary - based only on this scan's detected issues",
    }
