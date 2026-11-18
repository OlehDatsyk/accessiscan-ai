"""WCAG 2.2 reference data and the mapping from axe-core tags to success criteria.

Mappings are derived only from the tags that axe-core itself attaches to each rule (``wcag111`` ->
1.1.1). Rules tagged ``best-practice`` or without a WCAG tag are reported as best-practice issues and
are never given an invented success criterion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Criterion:
    number: str
    name: str
    level: str  # A | AA | AAA
    obsolete: bool = False


_RAW = """
1.1.1|Non-text Content|A
1.2.1|Audio-only and Video-only (Prerecorded)|A
1.2.2|Captions (Prerecorded)|A
1.2.3|Audio Description or Media Alternative (Prerecorded)|A
1.2.4|Captions (Live)|AA
1.2.5|Audio Description (Prerecorded)|AA
1.2.6|Sign Language (Prerecorded)|AAA
1.2.7|Extended Audio Description (Prerecorded)|AAA
1.2.8|Media Alternative (Prerecorded)|AAA
1.2.9|Audio-only (Live)|AAA
1.3.1|Info and Relationships|A
1.3.2|Meaningful Sequence|A
1.3.3|Sensory Characteristics|A
1.3.4|Orientation|AA
1.3.5|Identify Input Purpose|AA
1.3.6|Identify Purpose|AAA
1.4.1|Use of Color|A
1.4.2|Audio Control|A
1.4.3|Contrast (Minimum)|AA
1.4.4|Resize Text|AA
1.4.5|Images of Text|AA
1.4.6|Contrast (Enhanced)|AAA
1.4.7|Low or No Background Audio|AAA
1.4.8|Visual Presentation|AAA
1.4.9|Images of Text (No Exception)|AAA
1.4.10|Reflow|AA
1.4.11|Non-text Contrast|AA
1.4.12|Text Spacing|AA
1.4.13|Content on Hover or Focus|AA
2.1.1|Keyboard|A
2.1.2|No Keyboard Trap|A
2.1.3|Keyboard (No Exception)|AAA
2.1.4|Character Key Shortcuts|A
2.2.1|Timing Adjustable|A
2.2.2|Pause, Stop, Hide|A
2.2.3|No Timing|AAA
2.2.4|Interruptions|AAA
2.2.5|Re-authenticating|AAA
2.2.6|Timeouts|AAA
2.3.1|Three Flashes or Below Threshold|A
2.3.2|Three Flashes|AAA
2.3.3|Animation from Interactions|AAA
2.4.1|Bypass Blocks|A
2.4.2|Page Titled|A
2.4.3|Focus Order|A
2.4.4|Link Purpose (In Context)|A
2.4.5|Multiple Ways|AA
2.4.6|Headings and Labels|AA
2.4.7|Focus Visible|AA
2.4.8|Location|AAA
2.4.9|Link Purpose (Link Only)|AAA
2.4.10|Section Headings|AAA
2.4.11|Focus Not Obscured (Minimum)|AA
2.4.12|Focus Not Obscured (Enhanced)|AAA
2.4.13|Focus Appearance|AAA
2.5.1|Pointer Gestures|A
2.5.2|Pointer Cancellation|A
2.5.3|Label in Name|A
2.5.4|Motion Actuation|A
2.5.5|Target Size (Enhanced)|AAA
2.5.6|Concurrent Input Mechanisms|AAA
2.5.7|Dragging Movements|AA
2.5.8|Target Size (Minimum)|AA
3.1.1|Language of Page|A
3.1.2|Language of Parts|AA
3.1.3|Unusual Words|AAA
3.1.4|Abbreviations|AAA
3.1.5|Reading Level|AAA
3.1.6|Pronunciation|AAA
3.2.1|On Focus|A
3.2.2|On Input|A
3.2.3|Consistent Navigation|AA
3.2.4|Consistent Identification|AA
3.2.5|Change on Request|AAA
3.2.6|Consistent Help|A
3.3.1|Error Identification|A
3.3.2|Labels or Instructions|A
3.3.3|Error Suggestion|AA
3.3.4|Error Prevention (Legal, Financial, Data)|AA
3.3.5|Help|AAA
3.3.6|Error Prevention (All)|AAA
3.3.7|Redundant Entry|A
3.3.8|Accessible Authentication (Minimum)|AA
3.3.9|Accessible Authentication (Enhanced)|AAA
4.1.2|Name, Role, Value|A
4.1.3|Status Messages|AA
"""

CRITERIA: dict[str, Criterion] = {}
for _line in _RAW.strip().splitlines():
    _num, _name, _lvl = _line.split("|")
    CRITERIA[_num] = Criterion(_num, _name, _lvl)
# 4.1.1 Parsing was removed in WCAG 2.2; kept only so that legacy tags are labelled honestly.
CRITERIA["4.1.1"] = Criterion("4.1.1", "Parsing (obsolete, removed in WCAG 2.2)", "A", obsolete=True)

_LEVEL_ORDER = {"A": 0, "AA": 1, "AAA": 2}
_SC_TAG = re.compile(r"^wcag(\d)(\d)(\d{1,2})$")

CATEGORY_LABELS: dict[str, str] = {
    "images": "Images & text alternatives",
    "color": "Colour & contrast",
    "forms": "Forms",
    "aria": "ARIA",
    "names": "Names, roles & values",
    "keyboard": "Keyboard & focus",
    "structure": "Structure & landmarks",
    "semantics": "Semantics & headings",
    "language": "Language",
    "tables": "Tables",
    "parsing": "Parsing",
    "media": "Time & media",
    "sensory": "Sensory & visual cues",
    "links": "Links",
    "other": "Other",
}

_CAT_TAGS = {
    "cat.text-alternatives": "images",
    "cat.color": "color",
    "cat.forms": "forms",
    "cat.aria": "aria",
    "cat.name-role-value": "names",
    "cat.keyboard": "keyboard",
    "cat.structure": "structure",
    "cat.semantics": "semantics",
    "cat.language": "language",
    "cat.tables": "tables",
    "cat.parsing": "parsing",
    "cat.time-and-media": "media",
    "cat.sensory-and-visual-cues": "sensory",
}


def criteria_from_tags(tags: list[str]) -> list[str]:
    """Return WCAG success-criterion numbers explicitly tagged by the engine, in sorted order."""
    found: set[str] = set()
    for tag in tags:
        m = _SC_TAG.match(tag)
        if m:
            num = f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
            if num in CRITERIA:
                found.add(num)
    return sorted(found, key=lambda n: tuple(int(p) for p in n.split(".")))


def level_for(criteria: list[str]) -> str:
    """The least strict (lowest) conformance level among the mapped criteria, or '' if none."""
    levels = [CRITERIA[c].level for c in criteria if c in CRITERIA]
    if not levels:
        return ""
    return min(levels, key=lambda lv: _LEVEL_ORDER[lv])


def category_from_tags(tags: list[str], rule_id: str = "") -> str:
    for tag in tags:
        if tag in _CAT_TAGS:
            return _CAT_TAGS[tag]
    if rule_id.startswith("link") or "link" in rule_id:
        return "links"
    return "other"


def is_best_practice(tags: list[str], criteria: list[str]) -> bool:
    return "best-practice" in tags or not criteria


def describe(number: str) -> dict[str, str | bool]:
    c = CRITERIA.get(number)
    if c is None:
        return {"number": number, "name": "Unknown", "level": "", "obsolete": False}
    return {
        "number": c.number,
        "name": c.name,
        "level": c.level,
        "obsolete": c.obsolete,
        "url": understanding_url(c.number),
    }


_SLUGS = {
    # Slugs for W3C "Understanding" documents for the criteria automated rules most commonly map to.
    "1.1.1": "non-text-content",
    "1.3.1": "info-and-relationships",
    "1.3.5": "identify-input-purpose",
    "1.4.1": "use-of-color",
    "1.4.3": "contrast-minimum",
    "1.4.4": "resize-text",
    "1.4.6": "contrast-enhanced",
    "1.4.11": "non-text-contrast",
    "1.4.12": "text-spacing",
    "2.1.1": "keyboard",
    "2.2.1": "timing-adjustable",
    "2.2.2": "pause-stop-hide",
    "2.4.1": "bypass-blocks",
    "2.4.2": "page-titled",
    "2.4.4": "link-purpose-in-context",
    "2.4.9": "link-purpose-link-only",
    "2.5.3": "label-in-name",
    "2.5.8": "target-size-minimum",
    "3.1.1": "language-of-page",
    "3.1.2": "language-of-parts",
    "3.3.2": "labels-or-instructions",
    "4.1.2": "name-role-value",
}


def understanding_url(number: str) -> str:
    slug = _SLUGS.get(number)
    if slug:
        return f"https://www.w3.org/WAI/WCAG22/Understanding/{slug}.html"
    return "https://www.w3.org/WAI/WCAG22/quickref/"


# Criteria that automated testing cannot (fully) evaluate. Shown on every scan as a manual checklist.
MANUAL_REVIEW_CHECKS: list[dict[str, str]] = [
    {
        "criterion": "1.1.1",
        "title": "Alternative text is meaningful",
        "how": 'Automated tools only detect missing alt text. Check that each image\'s alternative conveys the same purpose, and that decorative images use alt="".',
    },
    {
        "criterion": "1.2.2",
        "title": "Captions for prerecorded video",
        "how": "Play each video with sound and confirm accurate, synchronised captions are available.",
    },
    {
        "criterion": "1.3.2",
        "title": "Meaningful reading order",
        "how": "Disable CSS or use a screen reader to confirm the content order still makes sense.",
    },
    {
        "criterion": "1.3.3",
        "title": "Instructions do not rely on sensory characteristics",
        "how": 'Look for instructions such as "click the round button on the right" that depend on shape, position or sound.',
    },
    {
        "criterion": "1.4.1",
        "title": "Colour is not the only visual means of conveying information",
        "how": "Check links, form errors, charts and status indicators for a non-colour cue (text, icon, underline, pattern).",
    },
    {
        "criterion": "1.4.4",
        "title": "Text can be resized to 200%",
        "how": "Zoom the browser to 200% and confirm no content or functionality is lost.",
    },
    {
        "criterion": "1.4.10",
        "title": "Content reflows at 320 CSS pixels",
        "how": "Set the viewport to 320px wide (or zoom to 400%) and confirm there is no two-dimensional scrolling for text content.",
    },
    {
        "criterion": "1.4.13",
        "title": "Content on hover or focus",
        "how": "Tooltips and popovers must be dismissible (Esc), hoverable, and persistent until dismissed.",
    },
    {
        "criterion": "2.1.1",
        "title": "All functionality is keyboard operable",
        "how": "Unplug the mouse. Use Tab, Shift+Tab, Enter, Space and arrow keys to complete every task on the page.",
    },
    {
        "criterion": "2.1.2",
        "title": "No keyboard trap",
        "how": "Tab through dialogs, embedded widgets and media players and confirm focus can always move away.",
    },
    {
        "criterion": "2.4.3",
        "title": "Logical focus order",
        "how": "Tab through the page and confirm focus moves in an order that preserves meaning and operability.",
    },
    {
        "criterion": "2.4.7",
        "title": "Focus is visible",
        "how": "Confirm every focusable element shows a clearly visible focus indicator.",
    },
    {
        "criterion": "2.4.11",
        "title": "Focused element is not obscured",
        "how": "Check that sticky headers, cookie banners or chat widgets do not fully hide the focused element.",
    },
    {
        "criterion": "2.5.3",
        "title": "Visible label is part of the accessible name",
        "how": "Compare each control's visible text with its accessible name (e.g. in browser dev tools).",
    },
    {
        "criterion": "3.2.1",
        "title": "No unexpected change on focus or input",
        "how": "Focusing or changing a control must not trigger navigation or major context changes without warning.",
    },
    {
        "criterion": "3.3.1",
        "title": "Errors are identified and described in text",
        "how": "Submit forms with invalid data and confirm errors are announced, described in text and linked to the field.",
    },
    {
        "criterion": "3.3.8",
        "title": "Accessible authentication",
        "how": "Login must not require a cognitive function test (e.g. transcribing a code) without an alternative such as paste or a password manager.",
    },
    {
        "criterion": "4.1.3",
        "title": "Status messages are announced",
        "how": "Use a screen reader to confirm search results counts, toasts and form success messages are announced without moving focus.",
    },
]
