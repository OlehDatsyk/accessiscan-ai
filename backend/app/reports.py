"""Report generation: PDF (ReportLab), CSV and DOCX (python-docx).

Every report states that it is an automated assessment and not a legal certification.
"""

from __future__ import annotations

import csv
import io
from collections import OrderedDict
from typing import Any
from xml.sax.saxutils import escape

from app import guidance, scoring, wcag

DISCLAIMER = (
    "This is an automated accessibility assessment produced by AccessiScan AI using axe-core in a real "
    "browser. It is not a legal certification and does not prove WCAG conformance or compliance with any law "
    "(such as the ADA, the European Accessibility Act or EN 301 549). Automated tools can detect only a "
    "portion of accessibility barriers; expert manual testing and testing with disabled users are required."
)
LIMITATIONS = [
    "Automated rules cover only part of WCAG 2.2. Many criteria (meaningful alternative text, logical focus "
    "order, keyboard traps, captions, error handling, cognitive accessibility) need human judgement.",
    "Only the pages listed in this report were tested, in their state at scan time, with a desktop viewport "
    "and without signing in. Content behind logins, paywalls or user interactions was not tested.",
    "'Needs review' items are potential issues that the engine could not confirm or rule out.",
    "The score is a relative indicator of automatically detected problems, not a conformance rating; a "
    "score of 100 does not mean the site is accessible.",
    "Issue matching between scans uses rule, page and CSS selector, and may be imperfect when the page "
    "structure changes.",
]
SEV_ORDER = {s: n for n, s in enumerate(scoring.SEVERITIES)}


def _safe_cell(value: Any) -> str:
    """Neutralise spreadsheet formula injection in CSV exports."""
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def _group(issues: list[Any]) -> OrderedDict[str, list[Any]]:
    groups: OrderedDict[str, list[Any]] = OrderedDict()
    for i in sorted(issues, key=lambda i: (0 if i.kind == "violation" else 1, SEV_ORDER.get(i.impact, 9), i.rule_id)):
        groups.setdefault(f"{i.kind}:{i.rule_id}", []).append(i)
    return groups


def _config_text(scan: Any) -> str:
    c = scan.config or {}
    parts = [f"mode={c.get('mode', scan.mode)}", f"max pages={c.get('max_pages', 1)}"]
    if c.get("mode") == "crawl":
        parts.append(f"max depth={c.get('max_depth', 0)}")
    parts.append("WCAG 2.2 A/AA + best practices" + (" + AAA" if c.get("include_aaa") else ""))
    return ", ".join(parts)


def build_csv(scan: Any, website: Any, issues: list[Any]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["# " + DISCLAIMER])
    w.writerow(
        [
            "website",
            "scan_id",
            "scan_date",
            "page_url",
            "rule_id",
            "type",
            "impact",
            "category",
            "wcag_criteria",
            "wcag_level",
            "best_practice",
            "summary",
            "description",
            "selector",
            "html_snippet",
            "failure_summary",
            "help_url",
            "status",
            "status_reason",
            "detected_by",
        ]
    )
    for i in issues:
        w.writerow(
            [
                _safe_cell(v)
                for v in (
                    website.url,
                    scan.id,
                    scan.created_at.isoformat(),
                    i.page_url,
                    i.rule_id,
                    "violation" if i.kind == "violation" else "needs review",
                    i.impact,
                    wcag.CATEGORY_LABELS.get(i.category, i.category),
                    " ".join(i.wcag_criteria or []),
                    i.wcag_level,
                    "yes" if i.is_best_practice else "no",
                    i.help,
                    i.description,
                    i.selector,
                    i.html_snippet,
                    i.failure_summary,
                    i.help_url,
                    i.status,
                    i.status_reason,
                    i.source,
                )
            ]
        )
    return ("﻿" + buf.getvalue()).encode("utf-8")


def build_pdf(
    scan: Any, website: Any, issues: list[Any], pages: list[Any], ai_suggestions: dict[str, dict[str, Any]]
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Accessibility report - {website.name}",
        author="AccessiScan AI",
        subject="Automated accessibility assessment",
        lang="en",
    )
    ss = getSampleStyleSheet()
    navy = colors.HexColor("#0f1f3d")
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], textColor=navy, fontSize=20, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=navy, fontSize=14, spaceBefore=10)
    h3 = ParagraphStyle("h3", parent=ss["Heading3"], textColor=navy, fontSize=11, spaceBefore=6)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9, leading=12, alignment=TA_LEFT)
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=10, textColor=colors.HexColor("#334155"))
    code = ParagraphStyle(
        "c",
        parent=body,
        fontName="Courier",
        fontSize=7.5,
        leading=9.5,
        backColor=colors.HexColor("#f1f5f9"),
        borderPadding=3,
    )
    note = ParagraphStyle(
        "n", parent=body, backColor=colors.HexColor("#fff7ed"), borderPadding=6, textColor=colors.HexColor("#7c2d12")
    )

    def P(text: Any, style: Any = body) -> Any:
        return Paragraph(escape(str(text)), style)

    def tbl(rows: list[list[Any]], widths: list[float] | None = None) -> Any:
        t = Table(rows, colWidths=widths, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), navy),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ]
            )
        )
        return t

    s = scan.summary or {}
    story: list[Any] = [
        P("Automated Accessibility Assessment", h1),
        P(f"{website.name} - {website.url}", h3),
        Spacer(1, 4),
        P(DISCLAIMER, note),
        Spacer(1, 8),
        tbl(
            [
                ["Item", "Value"],
                [P("Website URL"), P(website.url)],
                [P("Scan date (UTC)"), P(scan.created_at.strftime("%Y-%m-%d %H:%M"))],
                [P("Scan configuration"), P(_config_text(scan))],
                [P("Scanner version"), P(scan.scanner_version or "-")],
                [
                    P("Pages scanned / failed / blocked"),
                    P(f"{s.get('pages_scanned', 0)} / {s.get('pages_failed', 0)} / {s.get('pages_blocked', 0)}"),
                ],
                [P("Score (0-100)"), P(f"{scan.score if scan.score is not None else 'n/a'} - see methodology")],
            ],
            [55 * mm, 119 * mm],
        ),
        P("Results overview", h2),
        tbl(
            [
                ["Critical", "Serious", "Moderate", "Minor", "Needs review", "Passed checks", "Manual checks"],
                [str(s.get("by_impact", {}).get(k, 0)) for k in scoring.SEVERITIES]
                + [str(s.get("needs_review", 0)), str(s.get("passed_checks", 0)), str(s.get("manual_review_items", 0))],
            ]
        ),
        Spacer(1, 4),
        P("Counts are affected elements. Passed checks = sum over pages of axe rules that passed.", small),
        P("Scoring methodology", h2),
        P(scoring.methodology()["formula"], code),
        P(
            "Weights: critical 10, serious 6, moderate 3, minor 1. Needs-review items and manual checks do not "
            "affect the score. " + str(scoring.methodology()["disclaimer"]),
            small,
        ),
    ]
    if s.get("by_criterion"):
        story += [P("WCAG success criteria with detected violations", h2)]
        rows: list[list[Any]] = [["Criterion", "Name", "Level", "Elements"]]
        for num, count in s["by_criterion"].items():
            d = wcag.describe(num)
            rows.append([num, P(str(d["name"])), str(d["level"]), str(count)])
        story.append(tbl(rows, [22 * mm, 100 * mm, 18 * mm, 24 * mm]))
    if pages:
        story += [P("Pages", h2)]
        prow: list[list[Any]] = [["Page", "Status", "Score", "Violations", "Needs review"]]
        for p in pages:
            prow.append(
                [
                    P(p.final_url or p.url, small),
                    P(p.status + (f": {p.error}" if p.error else ""), small),
                    "-" if p.score is None else str(p.score),
                    str(p.violations_count),
                    str(p.needs_review_count),
                ]
            )
        story.append(tbl(prow, [80 * mm, 40 * mm, 16 * mm, 20 * mm, 20 * mm]))

    story += [PageBreak(), P("Detailed findings", h2)]
    groups = _group(issues)
    if not groups:
        story.append(
            P(
                "No automatically detectable issues were found on the scanned pages. This does not mean "
                "the pages are accessible - complete the manual review checklist below."
            )
        )
    for _key, items in groups.items():
        first = items[0]
        crit = (
            ", ".join(f"{c} {wcag.describe(c)['name']} ({wcag.describe(c)['level']})" for c in first.wcag_criteria)
            or "No WCAG mapping - accessibility best practice"
        )
        block: list[Any] = [
            P(f"{first.help or first.rule_id}", h3),
            P(
                f"Rule: {first.rule_id} | Type: {'violation' if first.kind == 'violation' else 'needs review (potential issue)'}"
                f" | Impact: {first.impact} | Elements: {len(items)} | Detected by: {first.source}",
                small,
            ),
            P(f"WCAG: {crit}", small),
            P(first.description),
        ]
        g = guidance.for_rule(first.rule_id)
        ai = ai_suggestions.get(str(first.id))
        if ai:
            block.append(
                P("AI-generated suggestion (review and test before applying): " + ai.get("recommended_fix", ""), small)
            )
        elif g:
            block.append(P("Recommended remediation (built-in guidance): " + g["fix"], small))
        elif first.help_url:
            block.append(P(f"Remediation guidance: {first.help_url}", small))
        story.append(KeepTogether(block))
        for i in items[:8]:
            story.append(P(f"{i.page_url}  -  {i.selector}", small))
            if i.html_snippet:
                story.append(P(i.html_snippet[:400], code))
            if i.status != "open":
                story.append(
                    P(
                        f"Status: {i.status}"
                        + (f" - {i.status_reason}" if i.status_reason else "")
                        + (" (marked manually, not verified by a re-scan)" if i.status == "marked_fixed" else ""),
                        small,
                    )
                )
        if len(items) > 8:
            story.append(P(f"... and {len(items) - 8} more elements (see the CSV export for the full list).", small))
        story.append(Spacer(1, 4))

    story += [
        PageBreak(),
        P("Manual review checklist", h2),
        P("These WCAG 2.2 criteria cannot be fully evaluated automatically and must be tested by a person.", small),
    ]
    mrows: list[list[Any]] = [["Criterion", "Check", "How to test"]]
    for m in wcag.MANUAL_REVIEW_CHECKS:
        mrows.append([m["criterion"], P(m["title"], small), P(m["how"], small)])
    story.append(tbl(mrows, [20 * mm, 50 * mm, 104 * mm]))
    story += [P("Limitations of automated testing", h2)] + [P("- " + text) for text in LIMITATIONS]

    def _footer(canvas: Any, d: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(18 * mm, 10 * mm, "AccessiScan AI - automated assessment, not a legal certification")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {d.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def build_docx(scan: Any, website: Any, issues: list[Any], pages: list[Any]) -> bytes:
    from docx import Document
    from docx.shared import Pt

    d = Document()
    d.core_properties.title = f"Accessibility report - {website.name}"
    d.core_properties.author = "AccessiScan AI"
    d.add_heading("Automated Accessibility Assessment", level=0)
    d.add_paragraph(f"{website.name} - {website.url}")
    d.add_paragraph(DISCLAIMER).italic = True
    s = scan.summary or {}
    t = d.add_table(rows=0, cols=2)
    t.style = "Light Grid Accent 1"
    for k, v in [
        ("Scan date (UTC)", scan.created_at.strftime("%Y-%m-%d %H:%M")),
        ("Scan configuration", _config_text(scan)),
        ("Scanner version", scan.scanner_version or "-"),
        ("Score (0-100)", "n/a" if scan.score is None else str(scan.score)),
        (
            "Critical / serious / moderate / minor",
            " / ".join(str(s.get("by_impact", {}).get(k, 0)) for k in scoring.SEVERITIES),
        ),
        ("Needs review", str(s.get("needs_review", 0))),
        ("Passed checks", str(s.get("passed_checks", 0))),
        ("Pages scanned", str(s.get("pages_scanned", 0))),
    ]:
        row = t.add_row().cells
        row[0].text, row[1].text = k, v
    d.add_heading("Scoring methodology", level=1)
    d.add_paragraph(str(scoring.methodology()["formula"]))
    d.add_paragraph(str(scoring.methodology()["disclaimer"]))
    d.add_heading("Detailed findings", level=1)
    for _key, items in _group(issues).items():
        first = items[0]
        d.add_heading(first.help or first.rule_id, level=2)
        crit = ", ".join(first.wcag_criteria) or "No WCAG mapping (best practice)"
        d.add_paragraph(
            f"Rule {first.rule_id} - {first.kind} - impact {first.impact} - WCAG {crit} - {len(items)} element(s)"
        )
        d.add_paragraph(first.description)
        g = guidance.for_rule(first.rule_id)
        if g:
            d.add_paragraph("Recommended remediation (built-in guidance): " + g["fix"])
        for i in items[:5]:
            p = d.add_paragraph(f"{i.page_url} - {i.selector}\n{i.html_snippet[:300]}")
            for r in p.runs:
                r.font.size = Pt(8)
    d.add_heading("Manual review checklist", level=1)
    for m in wcag.MANUAL_REVIEW_CHECKS:
        d.add_paragraph(f"{m['criterion']} {m['title']}: {m['how']}", style="List Bullet")
    d.add_heading("Limitations", level=1)
    for text in LIMITATIONS:
        d.add_paragraph(text, style="List Bullet")
    out = io.BytesIO()
    d.save(out)
    return out.getvalue()
