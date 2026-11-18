"""Page metadata extraction and a small set of supplementary heuristics (BeautifulSoup).

Heuristic findings are always reported as "needs review" (potential issues), never as confirmed
violations, and are labelled with ``source = accessiscan-heuristic``.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

GENERIC_LINK_TEXT = {
    "click here",
    "here",
    "read more",
    "more",
    "learn more",
    "click",
    "link",
    "this link",
    "more info",
    "details",
    "continue",
    "go",
}
_WS = re.compile(r"\s+")


def _text(el: Any) -> str:
    return _WS.sub(" ", el.get_text(" ", strip=True)).strip()


def _css_path(el: Any) -> str:
    parts: list[str] = []
    node = el
    while node is not None and getattr(node, "name", None) and node.name not in ("[document]", "html"):
        if node.get("id"):
            parts.append(f"#{node['id']}")
            break
        siblings = [s for s in node.parent.find_all(node.name, recursive=False)] if node.parent else [node]
        idx = siblings.index(node) + 1 if node in siblings else 1
        parts.append(f"{node.name}:nth-of-type({idx})" if len(siblings) > 1 else node.name)
        node = node.parent
    return " > ".join(reversed(parts))[:600]


def analyse_html(html: str, page_url: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    soup = BeautifulSoup(html, "html.parser")
    html_el = soup.find("html")
    title_el = soup.find("title")
    headings = []
    for h in soup.find_all(re.compile(r"^h[1-6]$"))[:200]:
        headings.append({"level": int(h.name[1]), "text": _text(h)[:150]})
    images = soup.find_all("img")
    meta: dict[str, Any] = {
        "title": _text(title_el) if title_el else "",
        "lang": (html_el.get("lang") or "").strip() if html_el else "",
        "has_meta_description": bool(soup.find("meta", attrs={"name": "description"})),
        "has_viewport": bool(soup.find("meta", attrs={"name": "viewport"})),
        "headings": headings,
        "counts": {
            "images": len(images),
            "images_missing_alt_attr": sum(1 for i in images if i.get("alt") is None),
            "links": len(soup.find_all("a", href=True)),
            "forms": len(soup.find_all("form")),
            "inputs": len(soup.find_all(["input", "select", "textarea"])),
            "buttons": len(soup.find_all("button")),
            "iframes": len(soup.find_all("iframe")),
            "landmarks": len(soup.find_all(["main", "nav", "header", "footer", "aside"]))
            + len(soup.find_all(attrs={"role": re.compile(r"^(main|navigation|banner|contentinfo|complementary)$")})),
        },
    }

    findings: list[dict[str, Any]] = []
    generic_nodes = []
    for a in soup.find_all("a", href=True):
        label = (a.get("aria-label") or "").strip().lower() or _text(a).lower()
        if label in GENERIC_LINK_TEXT and not a.get("aria-labelledby"):
            generic_nodes.append(
                {
                    "selector": _css_path(a),
                    "html": str(a)[:1200],
                    "failure_summary": (
                        f'Link text "{label}" may not describe the link\'s purpose. Check whether the surrounding '
                        "context (sentence, paragraph, list item or table cell) makes the purpose clear."
                    ),
                    "impact": "moderate",
                }
            )
    if generic_nodes:
        findings.append(
            {
                "id": "accessiscan-generic-link-text",
                "impact": "moderate",
                # 2.4.4 Link Purpose (In Context) is the criterion this heuristic relates to; it needs human
                # review because context can make generic text acceptable.
                "tags": ["cat.semantics", "wcag2a", "wcag244"],
                "description": 'Links with generic text such as "click here" or "read more" may not convey their purpose.',
                "help": "Link purpose may be unclear (potential issue - manual review needed)",
                "help_url": "https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-in-context.html",
                "nodes": generic_nodes[:50],
                "total_nodes": len(generic_nodes),
            }
        )
    return meta, findings
