"""Built-in (non-AI) remediation guidance for common axe-core rules.

Static, hand-written guidance shown when AI is not configured (and alongside AI output). Examples are
generic illustrations, not fixes generated for the specific page.
"""

from __future__ import annotations

from typing import Any

_G: dict[str, dict[str, Any]] = {
    "image-alt": {
        "fix": 'Give every informative image an alt attribute that conveys its purpose. Use alt="" for purely decorative images so screen readers skip them.',
        "before": '<img src="team.jpg">',
        "after": '<img src="team.jpg" alt="Our support team at the 2026 open day">',
        "users": ["Screen reader users", "Users with images disabled or slow connections"],
    },
    "color-contrast": {
        "fix": "Increase the contrast between text and its background to at least 4.5:1 (3:1 for large text: 24px, or 18.66px bold). Use the Contrast Checker to find a compliant colour pair.",
        "before": '<p style="color:#9a9a9a;background:#ffffff">Low contrast text</p>',
        "after": '<p style="color:#595959;background:#ffffff">Readable text (7:1)</p>',
        "users": ["Users with low vision or colour-vision deficiencies", "Anyone reading in bright sunlight"],
    },
    "label": {
        "fix": "Associate a visible <label> with each form field using for/id, or wrap the field in the label. Placeholder text is not a substitute for a label.",
        "before": '<input type="email" placeholder="Email">',
        "after": '<label for="email">Email address</label>\n<input id="email" type="email" autocomplete="email">',
        "users": ["Screen reader users", "Voice control users", "Users with cognitive disabilities"],
    },
    "button-name": {
        "fix": "Give every button an accessible name: visible text, or aria-label for icon-only buttons.",
        "before": "<button><svg>...</svg></button>",
        "after": '<button aria-label="Close dialog"><svg aria-hidden="true" focusable="false">...</svg></button>',
        "users": ["Screen reader users", "Voice control users"],
    },
    "link-name": {
        "fix": "Make sure every link has discernible text. For image links, put the destination in the image's alt text; for icon links, use aria-label.",
        "before": '<a href="/cart"><i class="icon-cart"></i></a>',
        "after": '<a href="/cart" aria-label="Shopping cart"><i class="icon-cart" aria-hidden="true"></i></a>',
        "users": ["Screen reader users", "Voice control users"],
    },
    "html-has-lang": {
        "fix": "Declare the primary language of the page on the <html> element.",
        "before": "<html>",
        "after": '<html lang="en">',
        "users": ["Screen reader users (correct pronunciation)", "Users relying on translation tools"],
    },
    "html-lang-valid": {
        "fix": "Use a valid BCP 47 language tag in the lang attribute, e.g. en, en-GB, uk, de.",
        "before": '<html lang="english">',
        "after": '<html lang="en">',
        "users": ["Screen reader users"],
    },
    "document-title": {
        "fix": "Give each page a unique, descriptive <title> that identifies its topic or purpose.",
        "before": "<head>...</head>",
        "after": "<head><title>Pricing - Example Ltd</title></head>",
        "users": ["Screen reader users", "Users with many tabs open", "Users with cognitive disabilities"],
    },
    "heading-order": {
        "fix": "Use headings in a logical order without skipping levels (h1 then h2 then h3). Choose the heading level for structure, and style it with CSS.",
        "before": "<h1>Products</h1>\n<h4>Laptops</h4>",
        "after": "<h1>Products</h1>\n<h2>Laptops</h2>",
        "users": ["Screen reader users navigating by headings"],
    },
    "page-has-heading-one": {
        "fix": "Add a single, visible <h1> describing the main content of the page.",
        "before": '<div class="title">Contact us</div>',
        "after": "<h1>Contact us</h1>",
        "users": ["Screen reader users navigating by headings"],
    },
    "landmark-one-main": {
        "fix": "Wrap the page's primary content in a single <main> element.",
        "before": '<div id="content">...</div>',
        "after": '<main id="content">...</main>',
        "users": ["Screen reader and keyboard users skipping to main content"],
    },
    "region": {
        "fix": "Place all page content inside landmark regions (header, nav, main, footer, aside).",
        "before": "<div>Promo banner</div>\n<main>...</main>",
        "after": "<header><div>Promo banner</div></header>\n<main>...</main>",
        "users": ["Screen reader users navigating by landmarks"],
    },
    "aria-valid-attr": {
        "fix": "Remove or correct misspelled or non-existent ARIA attributes.",
        "before": '<div aria-labeledby="title">',
        "after": '<div aria-labelledby="title">',
        "users": ["Screen reader users"],
    },
    "aria-required-attr": {
        "fix": "Provide all ARIA attributes required by the element's role, or use a native HTML element instead.",
        "before": '<div role="checkbox">Subscribe</div>',
        "after": '<label><input type="checkbox"> Subscribe</label>',
        "users": ["Screen reader users", "Keyboard users"],
    },
    "aria-roles": {
        "fix": "Use only valid WAI-ARIA role values, and prefer native HTML elements over ARIA roles.",
        "before": '<div role="buton">Save</div>',
        "after": '<button type="button">Save</button>',
        "users": ["Screen reader users"],
    },
    "duplicate-id-aria": {
        "fix": "Make IDs referenced by ARIA attributes or labels unique on the page.",
        "before": '<label for="name">Name</label><input id="name">\n<input id="name">',
        "after": '<label for="first-name">Name</label><input id="first-name">\n<input id="last-name">',
        "users": ["Screen reader users"],
    },
    "list": {
        "fix": "<ul> and <ol> must contain only <li>, <script> or <template> elements as direct children.",
        "before": "<ul><div>Item</div></ul>",
        "after": "<ul><li>Item</li></ul>",
        "users": ["Screen reader users"],
    },
    "frame-title": {
        "fix": "Give every <iframe> a title attribute describing its content.",
        "before": '<iframe src="map.html"></iframe>',
        "after": '<iframe src="map.html" title="Map of our office location"></iframe>',
        "users": ["Screen reader users"],
    },
    "meta-viewport": {
        "fix": "Do not disable zooming. Remove user-scalable=no and maximum-scale values below 2.",
        "before": '<meta name="viewport" content="width=device-width, user-scalable=no">',
        "after": '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "users": ["Users with low vision who zoom content"],
    },
    "select-name": {
        "fix": "Give every <select> a programmatically associated label.",
        "before": "<select>...</select>",
        "after": '<label for="country">Country</label>\n<select id="country">...</select>',
        "users": ["Screen reader users", "Voice control users"],
    },
    "accessiscan-generic-link-text": {
        "fix": "Make link text describe its destination, or add context with visually hidden text or aria-label that begins with the visible text.",
        "before": '<a href="/report.pdf">Click here</a>',
        "after": '<a href="/report.pdf">Download the 2026 annual report (PDF, 2 MB)</a>',
        "users": ["Screen reader users browsing a list of links", "Users with cognitive disabilities"],
    },
}


def for_rule(rule_id: str) -> dict[str, Any] | None:
    g = _G.get(rule_id)
    if g is None:
        return None
    return {"source": "built-in", "rule_id": rule_id, **g}
