import type { Impact } from "../api/types";

export function formatDate(iso: string | null | undefined, withTime = true): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" });
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86_400_000],
    ["hour", 3_600_000],
    ["minute", 60_000],
  ];
  for (const [unit, ms] of units) {
    if (abs >= ms) return rtf.format(-Math.round(diff / ms), unit);
  }
  return "just now";
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export const IMPACT_LABEL: Record<Impact, string> = {
  critical: "Critical",
  serious: "Serious",
  moderate: "Moderate",
  minor: "Minor",
};

export const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  in_progress: "In progress",
  marked_fixed: "Marked fixed",
  ignored: "Ignored",
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const CATEGORY_LABELS: Record<string, string> = {
  images: "Images & text alternatives",
  color: "Colour & contrast",
  forms: "Forms",
  aria: "ARIA",
  names: "Names, roles & values",
  keyboard: "Keyboard & focus",
  structure: "Structure & landmarks",
  semantics: "Semantics & headings",
  language: "Language",
  tables: "Tables",
  parsing: "Parsing",
  media: "Time & media",
  sensory: "Sensory & visual cues",
  links: "Links",
  other: "Other",
};

export function scoreBand(score: number | null | undefined): { label: string; className: string } {
  if (score === null || score === undefined) return { label: "Not scored", className: "text-slate-700" };
  if (score >= 90) return { label: "Few automated issues", className: "text-emerald-800" };
  if (score >= 70) return { label: "Needs work", className: "text-amber-800" };
  return { label: "Many automated issues", className: "text-red-800" };
}

export function hostOf(url: string | null | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}
