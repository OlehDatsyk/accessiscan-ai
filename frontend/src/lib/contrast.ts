/** WCAG 2.x contrast ratio (same algorithm as the backend `app/contrast.py`). */

export type RGB = [number, number, number];

const HEX = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i;
const RGB_RE = /^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*(?:0|1|0?\.\d+)\s*)?\)$/i;

export const THRESHOLDS = { aaNormal: 4.5, aaLarge: 3, aaaNormal: 7, aaaLarge: 4.5, nonText: 3 } as const;

export function parseColor(value: string): RGB | null {
  const v = value.trim();
  let m = HEX.exec(v);
  if (m) {
    let h = m[1];
    if (h.length === 3) h = h.split("").map((c) => c + c).join("");
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  m = RGB_RE.exec(v);
  if (m) {
    const rgb = [Number(m[1]), Number(m[2]), Number(m[3])] as RGB;
    return rgb.every((c) => c <= 255) ? rgb : null;
  }
  return null;
}

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

export function luminance([r, g, b]: RGB): number {
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(a: RGB, b: RGB): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

export function toHex([r, g, b]: RGB): string {
  return "#" + [r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("");
}

export function evaluate(fg: RGB, bg: RGB) {
  const ratio = contrastRatio(fg, bg);
  return {
    ratio,
    display: Math.floor(ratio * 100) / 100, // never round a failing ratio up to a passing display value
    aaNormal: ratio >= THRESHOLDS.aaNormal,
    aaLarge: ratio >= THRESHOLDS.aaLarge,
    aaaNormal: ratio >= THRESHOLDS.aaaNormal,
    aaaLarge: ratio >= THRESHOLDS.aaaLarge,
    nonText: ratio >= THRESHOLDS.nonText,
  };
}

/** Darken or lighten the foreground until it reaches the target ratio against the background. */
export function suggestForeground(fg: RGB, bg: RGB, target: number): RGB | null {
  if (contrastRatio(fg, bg) >= target) return fg;
  const darken = luminance(bg) > 0.18;
  let best: RGB | null = null;
  for (let step = 1; step <= 100; step++) {
    const t = step / 100;
    const c = fg.map((v) => Math.round(darken ? v * (1 - t) : v + (255 - v) * t)) as RGB;
    if (contrastRatio(c, bg) >= target) {
      best = c;
      break;
    }
  }
  return best;
}
