"""Transparent accessibility scoring model.

The score is an internal, relative indicator of how many automatically detectable problems a page has.
It is NOT a WCAG conformance rating, and 100 does not mean a page is accessible: automated rules cover
only a part of WCAG, so manual review is always required.

Per page:
    deduction(rule) = weight(impact) x (1 + 0.1 x min(affected_elements - 1, 10))
    page_score     = max(0, 100 - sum(deduction for each failed rule))
Scan score = arithmetic mean of the page scores of all successfully scanned pages.

Weights: critical 10, serious 6, moderate 3, minor 1. A rule that fails on many elements of a page
can therefore deduct at most twice its weight, so one widespread problem does not dominate the score.
"Needs review" results (axe "incomplete") and manual checks do not change the score.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

SEVERITY_WEIGHTS: dict[str, int] = {"critical": 10, "serious": 6, "moderate": 3, "minor": 1}
SEVERITIES = ("critical", "serious", "moderate", "minor")
EXTRA_NODE_FACTOR = 0.1
MAX_EXTRA_NODES = 10


def normalise_impact(impact: str | None) -> str:
    return impact if impact in SEVERITY_WEIGHTS else "moderate"


@dataclass(frozen=True)
class RuleFailure:
    rule_id: str
    impact: str
    nodes: int


def rule_deduction(impact: str, nodes: int) -> float:
    weight = SEVERITY_WEIGHTS[normalise_impact(impact)]
    extra = min(max(nodes - 1, 0), MAX_EXTRA_NODES)
    return round(weight * (1 + EXTRA_NODE_FACTOR * extra), 2)


def page_score(failures: Iterable[RuleFailure]) -> tuple[float, list[dict[str, object]]]:
    breakdown: list[dict[str, object]] = []
    total = 0.0
    for f in failures:
        d = rule_deduction(f.impact, f.nodes)
        total += d
        breakdown.append({"rule_id": f.rule_id, "impact": normalise_impact(f.impact), "nodes": f.nodes, "deduction": d})
    breakdown.sort(key=lambda b: -float(b["deduction"]))  # type: ignore[arg-type]
    return round(max(0.0, 100.0 - total), 1), breakdown


def scan_score(page_scores: Iterable[float | None]) -> float | None:
    vals = [s for s in page_scores if s is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def methodology() -> dict[str, object]:
    return {
        "weights": SEVERITY_WEIGHTS,
        "extra_node_factor": EXTRA_NODE_FACTOR,
        "max_extra_nodes": MAX_EXTRA_NODES,
        "formula": "page = max(0, 100 - sum(weight x (1 + 0.1 x min(elements - 1, 10)))); scan = mean(page scores)",
        "disclaimer": (
            "This score is a relative indicator of automatically detected problems. It is not an official "
            "WCAG conformance rating or legal certification, and a score of 100 does not prove that a page is "
            "accessible. Automated tools detect only a subset of accessibility barriers; manual testing is required."
        ),
    }
