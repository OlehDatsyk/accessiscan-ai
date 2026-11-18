export type Impact = "critical" | "serious" | "moderate" | "minor";
export const IMPACTS: Impact[] = ["critical", "serious", "moderate", "minor"];

export interface User {
  id: string;
  email: string;
  full_name: string;
  notify_scan_complete: boolean;
  notify_regressions: boolean;
  created_at: string;
}

export interface TokenOut {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

export interface Website {
  id: string;
  name: string;
  url: string;
  description: string;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  latest_score: number | null;
  latest_scan_id: string | null;
  latest_scan_at: string | null;
  latest_scan_status: string | null;
  scan_count: number;
  open_violations: number;
  monitoring_enabled: boolean;
}

export interface ScanSummary {
  pages_scanned?: number;
  pages_failed?: number;
  pages_blocked?: number;
  violations?: number;
  by_impact?: Record<Impact, number>;
  rules_by_impact?: Record<Impact, number>;
  failed_rules?: number;
  passed_checks?: number;
  passed_rules_unique?: number;
  needs_review?: number;
  manual_review_items?: number;
  best_practice_violations?: number;
  by_category?: Record<string, number>;
  by_criterion?: Record<string, number>;
  page_scores?: { url: string; score: number | null }[];
  stopped_reason?: string;
  blocked_requests?: number;
  blocked_hosts?: string[];
  robots_skipped?: number;
  carry_over?: { carried_ignored: number; regressed: number };
  vs_previous?: { scan_id: string; new: number; resolved: number; new_violations: number; resolved_violations: number; score_change: number | null };
}

export interface Scan {
  id: string;
  website_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  mode: "single" | "list" | "crawl";
  trigger: string;
  config: { urls?: string[]; mode?: string; max_pages?: number; max_depth?: number; include_aaa?: boolean; respect_robots?: boolean };
  pages_total: number;
  pages_done: number;
  progress_message: string;
  score: number | null;
  summary: ScanSummary;
  scanner_version: string;
  error_message: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  website_name: string | null;
  website_url: string | null;
}

export interface ScanPage {
  id: string;
  url: string;
  final_url: string;
  depth: number;
  status: string;
  http_status: number | null;
  title: string;
  lang: string;
  error: string;
  load_time_ms: number | null;
  score: number | null;
  violations_count: number;
  needs_review_count: number;
  passed_rules: string[];
  incomplete_rules: string[];
  inapplicable_count: number;
  page_metadata: {
    score_breakdown?: { rule_id: string; impact: Impact; nodes: number; deduction: number }[];
    headings?: { level: number; text: string }[];
    counts?: Record<string, number>;
    axe_version?: string;
  };
}

export interface Issue {
  id: string;
  scan_id: string;
  website_id: string;
  scan_page_id: string;
  rule_id: string;
  kind: "violation" | "needs_review";
  impact: Impact;
  category: string;
  wcag_criteria: string[];
  wcag_level: string;
  is_best_practice: boolean;
  description: string;
  help: string;
  help_url: string;
  failure_summary: string;
  selector: string;
  html_snippet: string;
  page_url: string;
  source: string;
  fingerprint: string;
  status: "open" | "in_progress" | "marked_fixed" | "ignored";
  status_reason: string;
  regressed: boolean;
  created_at: string;
  updated_at: string;
}

export interface AISuggestion {
  summary: string;
  why_it_matters: string;
  affected_users: string[];
  recommended_fix: string;
  code_before: string | null;
  code_after: string | null;
  code_language: string;
  verification_steps: string[];
  wcag_references: string[];
  caveats: string;
  provider?: string;
  model?: string;
  label?: string;
  cached?: boolean;
}

export interface IssueDetail extends Issue {
  notes: { id: string; body: string; created_at: string }[];
  history: { id: string; from_status: string; to_status: string; reason: string; actor_id: string | null; created_at: string }[];
  wcag_details: { number: string; name: string; level: string; url?: string; obsolete?: boolean }[];
  guidance: { fix: string; before: string; after: string; users: string[] } | null;
  ai_suggestion: AISuggestion | null;
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Facets {
  impact: Record<string, number>;
  category: Record<string, number>;
  wcag: Record<string, number>;
  status: Record<string, number>;
  kind: Record<string, number>;
  category_labels: Record<string, string>;
}

export interface Report {
  id: string;
  scan_id: string;
  format: "pdf" | "csv" | "docx";
  filename: string;
  size_bytes: number;
  created_at: string;
}

export interface Monitoring {
  id: string;
  website_id: string;
  enabled: boolean;
  frequency: "daily" | "weekly" | "monthly";
  scan_config: { mode?: string; max_pages?: number; max_depth?: number };
  notify_on_complete: boolean;
  notify_on_regression: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  website_name: string | null;
  website_url: string | null;
}

export interface Notification {
  id: string;
  kind: string;
  title: string;
  body: string;
  link: string;
  is_read: boolean;
  created_at: string;
}

export interface AIStatus {
  enabled: boolean;
  provider: string | null;
  model: string | null;
  daily_limit: number;
  used_today: number;
  message: string | null;
}

export interface ComparisonIssue {
  issue_id: string;
  rule_id: string;
  kind: string;
  impact: Impact;
  help: string;
  selector: string;
  page_url: string;
  wcag_criteria: string[];
  status: string;
}

export interface Comparison {
  base_scan_id: string;
  target_scan_id: string;
  base_date: string;
  target_date: string;
  score_base: number | null;
  score_target: number | null;
  score_change: number | null;
  counts: { new: number; resolved: number; remaining: number; new_violations: number; resolved_violations: number };
  impact_delta: Record<Impact, number>;
  passed_checks: { base: number; target: number; change: number };
  needs_review: { base: number; target: number; change: number };
  new_issues: ComparisonIssue[];
  resolved_issues: ComparisonIssue[];
  remaining_issues: ComparisonIssue[];
  severity_changes: { rule_id: string; selector: string; page_url: string; from: string; to: string; issue_id: string }[];
  note: string;
}

export interface ManualCheck {
  criterion: string;
  title: string;
  how: string;
  name: string;
  level: string;
}

export interface Methodology {
  weights: Record<Impact, number>;
  formula: string;
  disclaimer: string;
}
