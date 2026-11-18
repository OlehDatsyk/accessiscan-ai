"""WCAG 2.x contrast-ratio calculation (relative luminance, sRGB)."""

from __future__ import annotations

import re

_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_RGB = re.compile(r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*(?:0|1|0?\.\d+)\s*)?\)$", re.I)

AA_NORMAL, AA_LARGE, AAA_NORMAL, AAA_LARGE, NON_TEXT = 4.5, 3.0, 7.0, 4.5, 3.0


class ColorError(ValueError):
    pass


def parse_color(value: str) -> tuple[int, int, int]:
    v = value.strip()
    m = _HEX.match(v)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    m = _RGB.match(v)
    if m:
        rgb = tuple(int(x) for x in m.groups()[:3])
        if any(c > 255 for c in rgb):
            raise ColorError("RGB channel values must be between 0 and 255")
        return rgb  # type: ignore[return-value]
    raise ColorError("Use a HEX colour (#1a2b3c or #abc) or rgb(r, g, b)")


def _channel(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (_channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def evaluate(foreground: str, background: str) -> dict[str, object]:
    fg, bg = parse_color(foreground), parse_color(background)
    ratio = contrast_ratio(fg, bg)
    # Compare against thresholds without rounding up (4.499 must fail 4.5).
    return {
        "foreground": "#{:02x}{:02x}{:02x}".format(*fg),
        "background": "#{:02x}{:02x}{:02x}".format(*bg),
        "ratio": round(ratio, 2),
        "ratio_exact": ratio,
        "aa_normal": ratio >= AA_NORMAL,
        "aa_large": ratio >= AA_LARGE,
        "aaa_normal": ratio >= AAA_NORMAL,
        "aaa_large": ratio >= AAA_LARGE,
        "non_text": ratio >= NON_TEXT,
    }
