"""Domain services shared by the API and the worker: persisting scan results, summaries, comparisons,
activity logs and notifications."""

from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import scoring, wcag
from app.db import utcnow
from app.models import ActivityLog, Issue, IssueStatusHistory, Notification, Scan, ScanPage, User

ACTIVE_STATUSES = ("queued", "running")


def log_activity(
    db: Session, owner_id: uuid.UUID, action: str, entity_type: str = "", entity_id: Any = "", detail: str = ""
) -> None:
    db.add(
        ActivityLog(
            owner_id=owner_id, action=action, entity_type=entity_type, entity_id=str(entity_id), detail=detail[:500]
        )
    )


def notify(db: Session, owner_id: uuid.UUID, kind: str, title: str, body: str = "", link: str = "") -> None:
    db.add(Notification(owner_id=owner_id, kind=kind, title=title[:200], body=body[:2000], link=link[:500]))


def page_key(url: str) -> str:
    """Stable page identifier for matching across scans: host + path + query, without scheme/fragment."""
    p = urlsplit(url)
    path = p.path.rstrip("/") or "/"
    return f"{(p.hostname or '').lower()}{path}{('?' + p.query) if p.query else ''}"


def fingerprint(rule_id: str, page_url: str, selector: str) -> str:
    return hashlib.sha256(f"{rule_id}|{page_key(page_url)}|{selector.strip()}".encode()).hexdigest()


def persist_page(db: Session, scan: Scan, result: Any) -> ScanPage:
    """Store one scanned page and its issues in a single transaction."""
    page = ScanPage(
        scan_id=scan.id,
        url=result.url[:2048],
        final_url=(result.final_url or "")[:2048],
        depth=result.depth,
        status=result.status,
        http_status=result.http_status,
        title=result.title,
        lang=result.lang,
        error=result.error[:2000],
        load_time_ms=result.load_time_ms,
        passed_rules=result.passed_rules,
        incomplete_rules=result.incomplete_rules,
        inapplicable_count=result.inapplicable_count,
        page_metadata=result.metadata,
    )
    db.add(page)
    db.flush()
    page_url = result.final_url or result.url
    seen: set[str] = set()
    violations_count = needs_review_count = 0

    def add_rule(rule: dict[str, Any], kind: str, source: str) -> int:
        tags = rule.get("tags", [])
        criteria = wcag.criteria_from_tags(tags)
        added = 0
        for node in rule.get("nodes", []):
            fp = fingerprint(rule["id"], page_url, node.get("selector", ""))
            if fp in seen:
                continue
            seen.add(fp)
            db.add(
                Issue(
                    owner_id=scan.owner_id,
                    website_id=scan.website_id,
                    scan_id=scan.id,
                    scan_page_id=page.id,
                    rule_id=rule["id"],
                    kind=kind,
                    impact=scoring.normalise_impact(node.get("impact") or rule.get("impact")),
                    category=wcag.category_from_tags(tags, rule["id"]),
                    wcag_criteria=criteria,
                    wcag_level=wcag.level_for(criteria),
                    is_best_practice=wcag.is_best_practice(tags, criteria),
                    description=rule.get("description", ""),
                    help=rule.get("help", ""),
                    help_url=rule.get("help_url", ""),
                    failure_summary=node.get("failure_summary", ""),
                    selector=node.get("selector", ""),
                    html_snippet=node.get("html", ""),
                    page_url=page_url[:2048],
                    source=source,
                    fingerprint=fp,
                )
            )
            added += 1
        return added

    axe_source = f"axe-core {result.metadata.get('axe_version', '')}".strip()
    failures = []
    for rule in result.violations:
        violations_count += add_rule(rule, "violation", axe_source)
        failures.append(scoring.RuleFailure(rule["id"], rule.get("impact") or "moderate", rule.get("total_nodes", 1)))
    for rule in result.incomplete:
        needs_review_count += add_rule(rule, "needs_review", axe_source)
    for rule in result.heuristics:
        needs_review_count += add_rule(rule, "needs_review", "accessiscan-heuristic")

    if result.status == "ok":
        page.score, breakdown = scoring.page_score(failures)
        page.page_metadata = {**result.metadata, "score_breakdown": breakdown}
    page.violations_count = violations_count
    page.needs_review_count = needs_review_count
    return page


def build_summary(db: Session, scan: Scan) -> dict[str, Any]:
    pages = list(db.scalars(select(ScanPage).where(ScanPage.scan_id == scan.id)))
    rows = db.execute(
        select(Issue.kind, Issue.impact, Issue.rule_id, Issue.category, Issue.wcag_criteria, Issue.status).where(
            Issue.scan_id == scan.id
        )
    ).all()
    by_impact: Counter[str] = Counter()
    rules_by_impact: dict[str, set[str]] = {s: set() for s in scoring.SEVERITIES}
    by_category: Counter[str] = Counter()
    by_criterion: Counter[str] = Counter()
    needs_review = 0
    best_practice = 0
    for kind, impact, rule_id, category, criteria, _status in rows:
        if kind == "violation":
            by_impact[impact] += 1
            rules_by_impact.setdefault(impact, set()).add(rule_id)
            by_category[category] += 1
            if criteria:
                for c in criteria:
                    by_criterion[c] += 1
            else:
                best_practice += 1
        else:
            needs_review += 1
    ok_pages = [p for p in pages if p.status == "ok"]
    passed_unique = set().union(*[set(p.passed_rules) for p in ok_pages]) if ok_pages else set()
    failed_unique = set().union(*rules_by_impact.values())
    return {
        "pages_scanned": len(ok_pages),
        "pages_failed": sum(1 for p in pages if p.status == "failed"),
        "pages_blocked": sum(1 for p in pages if p.status == "blocked"),
        "violations": sum(by_impact.values()),
        "by_impact": {s: by_impact.get(s, 0) for s in scoring.SEVERITIES},
        "rules_by_impact": {s: len(rules_by_impact.get(s, set())) for s in scoring.SEVERITIES},
        "failed_rules": len(failed_unique),
        "passed_checks": sum(len(p.passed_rules) for p in ok_pages),
        "passed_rules_unique": len(passed_unique - failed_unique),
        "needs_review": needs_review,
        "manual_review_items": len(wcag.MANUAL_REVIEW_CHECKS),
        "best_practice_violations": best_practice,
        "by_category": dict(by_category.most_common()),
        "by_criterion": dict(sorted(by_criterion.items(), key=lambda kv: [int(x) for x in kv[0].split(".")])),
        "page_scores": [{"url": p.final_url or p.url, "score": p.score} for p in ok_pages],
    }


def previous_completed_scan(db: Session, scan: Scan) -> Scan | None:
    return db.scalar(
        select(Scan)
        .where(
            Scan.website_id == scan.website_id,
            Scan.status == "completed",
            Scan.id != scan.id,
            Scan.created_at < scan.created_at,
        )
        .order_by(Scan.created_at.desc())
        .limit(1)
    )


def carry_over_statuses(db: Session, scan: Scan, previous: Scan | None) -> dict[str, int]:
    """Carry 'ignored' decisions forward; flag issues that were marked fixed but are detected again."""
    if previous is None:
        return {"carried_ignored": 0, "regressed": 0}
    prev = {
        fp: (status, reason)
        for fp, status, reason in db.execute(
            select(Issue.fingerprint, Issue.status, Issue.status_reason).where(Issue.scan_id == previous.id)
        ).all()
    }
    carried = regressed = 0
    for issue in db.scalars(select(Issue).where(Issue.scan_id == scan.id)):
        if issue.fingerprint not in prev:
            continue
        status, reason = prev[issue.fingerprint]
        if status == "ignored":
            issue.status, issue.status_reason = "ignored", reason
            db.add(
                IssueStatusHistory(
                    issue_id=issue.id,
                    actor_id=None,
                    from_status="open",
                    to_status="ignored",
                    reason=f"Carried over from previous scan: {reason}"[:2000],
                )
            )
            carried += 1
        elif status == "marked_fixed":
            issue.regressed = True
            db.add(
                IssueStatusHistory(
                    issue_id=issue.id,
                    actor_id=None,
                    from_status="",
                    to_status="open",
                    reason="Marked as fixed in the previous scan but detected again by the scanner",
                )
            )
            regressed += 1
    return {"carried_ignored": carried, "regressed": regressed}


def compare_scans(db: Session, base: Scan, target: Scan) -> dict[str, Any]:
    """Compare two scans of the same website by issue fingerprint (rule + page + element selector)."""

    def load(scan: Scan) -> dict[str, Issue]:
        return {i.fingerprint: i for i in db.scalars(select(Issue).where(Issue.scan_id == scan.id))}

    a, b = load(base), load(target)
    new_fps = b.keys() - a.keys()
    resolved_fps = a.keys() - b.keys()
    remaining_fps = a.keys() & b.keys()
    severity_changes = []
    for fp in remaining_fps:
        if a[fp].impact != b[fp].impact or a[fp].kind != b[fp].kind:
            severity_changes.append(
                {
                    "rule_id": b[fp].rule_id,
                    "selector": b[fp].selector[:200],
                    "page_url": b[fp].page_url,
                    "from": f"{a[fp].kind}/{a[fp].impact}",
                    "to": f"{b[fp].kind}/{b[fp].impact}",
                    "issue_id": str(b[fp].id),
                }
            )

    def brief(i: Issue) -> dict[str, Any]:
        return {
            "issue_id": str(i.id),
            "rule_id": i.rule_id,
            "kind": i.kind,
            "impact": i.impact,
            "help": i.help,
            "selector": i.selector[:200],
            "page_url": i.page_url,
            "wcag_criteria": i.wcag_criteria,
            "status": i.status,
        }

    def violations(d: dict[str, Issue], fps: Any) -> list[Issue]:
        return [d[fp] for fp in fps]

    sa, sb = base.summary or {}, target.summary or {}
    order = {s: n for n, s in enumerate(scoring.SEVERITIES)}

    def sort_key(i: Issue) -> tuple[int, int, str]:
        return (0 if i.kind == "violation" else 1, order.get(i.impact, 9), i.rule_id)

    new = sorted(violations(b, new_fps), key=sort_key)
    resolved = sorted(violations(a, resolved_fps), key=sort_key)
    remaining = sorted(violations(b, remaining_fps), key=sort_key)
    impact_delta = {
        s: (sb.get("by_impact", {}).get(s, 0) - sa.get("by_impact", {}).get(s, 0)) for s in scoring.SEVERITIES
    }
    return {
        "base_scan_id": str(base.id),
        "target_scan_id": str(target.id),
        "base_date": base.created_at.isoformat(),
        "target_date": target.created_at.isoformat(),
        "score_base": base.score,
        "score_target": target.score,
        "score_change": (
            round(target.score - base.score, 1) if base.score is not None and target.score is not None else None
        ),
        "counts": {
            "new": len(new),
            "resolved": len(resolved),
            "remaining": len(remaining),
            "new_violations": sum(1 for i in new if i.kind == "violation"),
            "resolved_violations": sum(1 for i in resolved if i.kind == "violation"),
        },
        "impact_delta": impact_delta,
        "passed_checks": {
            "base": sa.get("passed_checks", 0),
            "target": sb.get("passed_checks", 0),
            "change": sb.get("passed_checks", 0) - sa.get("passed_checks", 0),
        },
        "needs_review": {
            "base": sa.get("needs_review", 0),
            "target": sb.get("needs_review", 0),
            "change": sb.get("needs_review", 0) - sa.get("needs_review", 0),
        },
        "new_issues": [brief(i) for i in new[:500]],
        "resolved_issues": [brief(i) for i in resolved[:500]],
        "remaining_issues": [brief(i) for i in remaining[:500]],
        "severity_changes": severity_changes[:500],
        "note": (
            "Issues are matched by rule, page and CSS selector. Changes to page structure (for example "
            "re-ordered elements or generated class names) can make an unchanged problem appear as both "
            "'resolved' and 'new', so treat matching as approximate."
        ),
    }


def finalize_scan(db: Session, scan: Scan, outcome: Any) -> None:
    pages = list(db.scalars(select(ScanPage).where(ScanPage.scan_id == scan.id)))
    scan.score = scoring.scan_score(p.score for p in pages if p.status == "ok")
    summary = build_summary(db, scan)
    previous = previous_completed_scan(db, scan)
    summary["carry_over"] = carry_over_statuses(db, scan, previous)
    summary["stopped_reason"] = getattr(outcome, "stopped_reason", "")
    summary["blocked_requests"] = len(getattr(outcome, "blocked_requests", []) or [])
    summary["blocked_hosts"] = sorted({b["host"] for b in getattr(outcome, "blocked_requests", []) or []})[:20]
    summary["bytes_downloaded"] = getattr(outcome, "bytes_downloaded", 0)
    summary["robots_skipped"] = getattr(outcome, "robots_skipped", 0)
    if previous is not None:
        db.flush()
        cmp = compare_scans(db, previous, scan)
        summary["vs_previous"] = {"scan_id": str(previous.id), **cmp["counts"], "score_change": cmp["score_change"]}
    scan.summary = summary
    scan.pages_done = len(pages)
    now = utcnow()
    scan.finished_at = now
    if summary["pages_scanned"] == 0:
        scan.status = "failed"
        reasons = "; ".join(sorted({p.error for p in pages if p.error}))[:900]
        scan.error_message = scan.error_message or (reasons or "No page could be scanned")
    else:
        scan.status = "completed"
    user = db.get(User, scan.owner_id)
    site_name = scan.website.name if scan.website else "website"
    want_complete = user.notify_scan_complete if user else False
    want_regress = user.notify_regressions if user else False
    if scan.trigger == "schedule" and scan.website is not None and scan.website.monitoring is not None:
        want_complete = scan.website.monitoring.notify_on_complete
        want_regress = scan.website.monitoring.notify_on_regression
    if user is not None:
        if scan.status == "completed" and want_complete:
            notify(
                db,
                user.id,
                "scan_completed",
                f"Scan completed: {site_name}",
                f"Score {scan.score if scan.score is not None else '-'} - {summary['violations']} violations, "
                f"{summary['needs_review']} items need review.",
                f"/scans/{scan.id}",
            )
        if scan.status == "failed":
            notify(
                db, user.id, "scan_failed", f"Scan failed: {site_name}", scan.error_message[:500], f"/scans/{scan.id}"
            )
        vs = summary.get("vs_previous")
        if vs and want_regress and (vs.get("new_violations") or summary["carry_over"]["regressed"]):
            notify(
                db,
                user.id,
                "regression",
                f"New accessibility issues on {site_name}",
                f"{vs.get('new_violations', 0)} new violations since the previous scan; "
                f"{summary['carry_over']['regressed']} issues marked fixed were detected again.",
                f"/scans/{scan.id}",
            )


def reset_scan_results(db: Session, scan: Scan) -> None:
    db.execute(delete(Issue).where(Issue.scan_id == scan.id))
    db.execute(delete(ScanPage).where(ScanPage.scan_id == scan.id))


def count_active_scans(db: Session, owner_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(Scan).where(Scan.owner_id == owner_id, Scan.status.in_(ACTIVE_STATUSES))
        )
        or 0
    )
