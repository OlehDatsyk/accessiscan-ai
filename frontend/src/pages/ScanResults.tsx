import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Download, GitCompare, Info, Square } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, downloadReport, post } from "../api/client";
import type { AIStatus, ManualCheck, Methodology, Report, Scan, ScanPage } from "../api/types";
import { IssuesTable } from "../components/IssuesTable";
import { usePageTitle } from "../components/Layout";
import { Alert, Button, ButtonLink, Card, Dialog, PageHeader, ScoreRing, Spinner, StatusBadge, TabPanel, Tabs } from "../components/ui";
import { formatDate, scoreBand } from "../lib/format";

type Tab = "issues" | "pages" | "manual" | "score";

interface AISummary {
  executive_summary: string;
  top_priorities: { rule_id: string; title: string; reason: string }[];
  quick_wins: string[];
  caveats: string;
  label: string;
  provider: string;
  model: string;
}

export default function ScanResults() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("issues");
  const [methodOpen, setMethodOpen] = useState(false);
  const [reportMsg, setReportMsg] = useState<string | null>(null);

  const scan = useQuery({
    queryKey: ["scan", id],
    queryFn: () => api<Scan>(`/scans/${id}`),
    refetchInterval: (q) => (q.state.data && ["queued", "running"].includes(q.state.data.status) ? 2500 : false),
  });
  usePageTitle(scan.data ? `Scan of ${scan.data.website_name}` : "Scan results");
  const done = scan.data?.status === "completed" || scan.data?.status === "cancelled";
  const pages = useQuery({ queryKey: ["scan-pages", id, scan.data?.pages_done], queryFn: () => api<ScanPage[]>(`/scans/${id}/pages`), enabled: !!scan.data });
  const manual = useQuery({ queryKey: ["manual-checks"], queryFn: () => api<ManualCheck[]>("/wcag/manual-checks"), staleTime: Infinity });
  const method = useQuery({ queryKey: ["methodology"], queryFn: () => api<Methodology>("/scoring/methodology"), staleTime: Infinity });
  const aiStatus = useQuery({ queryKey: ["ai-status"], queryFn: () => api<AIStatus>("/ai/status") });

  const cancel = useMutation({ mutationFn: () => post<Scan>(`/scans/${id}/cancel`), onSuccess: () => qc.invalidateQueries({ queryKey: ["scan", id] }) });
  const report = useMutation({
    mutationFn: (format: string) => post<Report>("/reports", { scan_id: id, format }),
    onSuccess: async (r) => {
      qc.invalidateQueries({ queryKey: ["reports"] });
      await downloadReport(r.id, r.filename);
      setReportMsg(`${r.format.toUpperCase()} report generated and downloaded (${r.filename}).`);
    },
  });
  const summary = useMutation({ mutationFn: () => post<AISummary>(`/ai/scans/${id}/summary`) });

  if (scan.isLoading) return <Spinner label="Loading scan" />;
  if (scan.error) return <Alert tone="error" title="Scan not found">{(scan.error as Error).message}</Alert>;
  const s = scan.data!;
  const sum = s.summary ?? {};
  const band = scoreBand(s.score);
  const active = s.status === "queued" || s.status === "running";
  const prev = sum.vs_previous;

  return (
    <>
      <PageHeader
        title={`Scan results: ${s.website_name ?? "website"}`}
        description={
          <>
            <StatusBadge status={s.status} /> <span className="ml-1">Started {formatDate(s.created_at)} · {s.mode === "crawl" ? `Crawl (up to ${s.config.max_pages} pages, depth ${s.config.max_depth})` : s.mode === "list" ? `${s.config.urls?.length ?? 0} URLs` : "Single page"}</span>
          </>
        }
        actions={
          <>
            {active && <Button variant="secondary" loading={cancel.isPending} onClick={() => cancel.mutate()} icon={<Square className="h-4 w-4" aria-hidden="true" />}>Cancel scan</Button>}
            {prev && <ButtonLink variant="secondary" to={`/compare?base=${prev.scan_id}&target=${s.id}`}><GitCompare className="h-4 w-4" aria-hidden="true" />Compare with previous</ButtonLink>}
            {done && <ButtonLink variant="secondary" to={`/assistant?scan=${s.id}`}><Bot className="h-4 w-4" aria-hidden="true" />Ask the assistant</ButtonLink>}
          </>
        }
      />

      {active && (
        <div role="status" aria-live="polite" className="mb-6 rounded-xl border border-sky-200 bg-sky-50 p-4">
          <h2 className="font-medium text-sky-950">{s.status === "queued" ? "Waiting for a scanner worker…" : s.progress_message || "Scanning…"}</h2>
          <div className="mt-2 h-2 w-full overflow-hidden rounded bg-sky-100">
            <div className="h-2 bg-sky-700" style={{ width: `${Math.min(100, Math.round((s.pages_done / Math.max(1, s.pages_total)) * 100))}%` }} />
          </div>
          <p className="mt-1 text-sm text-sky-950">{s.pages_done} of up to {s.pages_total} page{s.pages_total === 1 ? "" : "s"} scanned</p>
        </div>
      )}
      {s.status === "failed" && <Alert tone="error" className="mb-6" title="The scan failed">{s.error_message || "Unknown error"}</Alert>}
      {s.status === "cancelled" && <Alert tone="warning" className="mb-6" title="The scan was cancelled">Results below cover only the pages scanned before cancellation.</Alert>}
      {sum.stopped_reason && done && <Alert tone="info" className="mb-6">Scan stopped early: {sum.stopped_reason}.</Alert>}

      {(done || s.status === "failed") && (
        <section aria-labelledby="overview-h" className="mb-6">
          <h2 id="overview-h" className="sr-only">Overview</h2>
          <div className="grid gap-4 lg:grid-cols-4">
            <Card className="flex min-w-0 flex-col items-center gap-3 text-center sm:flex-row sm:text-left lg:col-span-1 lg:flex-col lg:text-center">
              <ScoreRing score={s.score} />
              <div>
                <p className={`font-semibold ${band.className}`}>{band.label}</p>
                <button type="button" onClick={() => setMethodOpen(true)} className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-navy-800 underline">
                  <Info className="h-4 w-4 shrink-0" aria-hidden="true" /><span>How is this calculated?</span>
                </button>
              </div>
            </Card>
            <Card className="lg:col-span-3">
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                {(["critical", "serious", "moderate", "minor"] as const).map((k) => (
                  <div key={k}>
                    <dt className="text-sm capitalize text-slate-700">{k}</dt>
                    <dd className="text-2xl font-semibold">{sum.by_impact?.[k] ?? 0}</dd>
                    <dd className="text-xs text-slate-700">{sum.rules_by_impact?.[k] ?? 0} rule{sum.rules_by_impact?.[k] === 1 ? "" : "s"}</dd>
                  </div>
                ))}
                <div><dt className="text-sm text-slate-700">Passed checks</dt><dd className="text-2xl font-semibold">{sum.passed_checks ?? 0}</dd></div>
                <div><dt className="text-sm text-slate-700">Needs review</dt><dd className="text-2xl font-semibold">{sum.needs_review ?? 0}</dd></div>
                <div><dt className="text-sm text-slate-700">Manual checks</dt><dd className="text-2xl font-semibold">{sum.manual_review_items ?? 0}</dd></div>
                <div><dt className="text-sm text-slate-700">Pages scanned</dt><dd className="text-2xl font-semibold">{sum.pages_scanned ?? 0}</dd>{(sum.pages_failed || sum.pages_blocked) ? <dd className="text-xs text-slate-700">{sum.pages_failed ?? 0} failed, {sum.pages_blocked ?? 0} blocked</dd> : null}</div>
              </dl>
              {prev && (
                <p className="mt-4 text-sm text-slate-800">
                  Since the previous scan: <strong>{prev.new_violations}</strong> new and <strong>{prev.resolved_violations}</strong> resolved violations
                  {prev.score_change !== null && <> · score {prev.score_change >= 0 ? "+" : ""}{prev.score_change}</>}.
                </p>
              )}
              {!!sum.blocked_requests && <p className="mt-2 text-xs text-slate-700">{sum.blocked_requests} network request(s) were blocked by the scanner's security policy (for example requests to private networks).</p>}
            </Card>
          </div>
        </section>
      )}

      {done && (
        <Card className="mb-6" aria-labelledby="reports-h">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 id="reports-h" className="font-semibold text-navy-900">Reports</h2>
              <p className="text-sm text-slate-700">Automated assessment reports – not legal certification.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {["pdf", "csv", "docx"].map((fmt) => (
                <Button key={fmt} variant="secondary" loading={report.isPending && report.variables === fmt} onClick={() => report.mutate(fmt)} icon={<Download className="h-4 w-4" aria-hidden="true" />}>
                  {fmt.toUpperCase()}<span className="sr-only"> report</span>
                </Button>
              ))}
            </div>
          </div>
          {reportMsg && <Alert tone="success" live className="mt-3">{reportMsg}</Alert>}
          {report.error && <Alert tone="error" live className="mt-3">{(report.error as Error).message}</Alert>}
        </Card>
      )}

      {done && (sum.violations ?? 0) > 0 && (
        <Card className="mb-6" aria-labelledby="ai-sum-h">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 id="ai-sum-h" className="font-semibold text-navy-900">AI audit summary and priorities</h2>
              <p className="text-sm text-slate-700">{aiStatus.data?.enabled ? "Generated only from this scan's detected issues." : aiStatus.data?.message}</p>
            </div>
            <Button variant="secondary" disabled={!aiStatus.data?.enabled} loading={summary.isPending} onClick={() => summary.mutate()} icon={<Bot className="h-4 w-4" aria-hidden="true" />}>
              {summary.data ? "Regenerate summary" : "Generate summary"}
            </Button>
          </div>
          {summary.error && <Alert tone="error" live className="mt-3">{(summary.error as Error).message}</Alert>}
          {summary.data && (
            <div className="mt-4 space-y-3 text-sm" aria-live="polite">
              <p className="inline-block rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-950">{summary.data.label}</p>
              <p>{summary.data.executive_summary}</p>
              {summary.data.top_priorities.length > 0 && (
                <>
                  <h3 className="font-semibold">Fix first</h3>
                  <ol className="list-decimal space-y-1 pl-5">
                    {summary.data.top_priorities.map((p) => (
                      <li key={p.rule_id}><strong>{p.title}</strong> <code className="text-xs">({p.rule_id})</code> – {p.reason}</li>
                    ))}
                  </ol>
                </>
              )}
              {summary.data.quick_wins.length > 0 && (
                <>
                  <h3 className="font-semibold">Quick wins</h3>
                  <ul className="list-disc pl-5">{summary.data.quick_wins.map((q) => <li key={q}>{q}</li>)}</ul>
                </>
              )}
              {summary.data.caveats && <p className="text-slate-700">{summary.data.caveats}</p>}
              <p className="text-xs text-slate-700">Model: {summary.data.provider} / {summary.data.model}</p>
            </div>
          )}
        </Card>
      )}

      {(done || (pages.data?.length ?? 0) > 0) && (
        <>
          <Tabs
            idPrefix="scan"
            label="Scan result sections"
            value={tab}
            onChange={setTab}
            tabs={[
              { id: "issues", label: "Issues", count: (sum.violations ?? 0) + (sum.needs_review ?? 0) },
              { id: "pages", label: "Pages", count: pages.data?.length },
              { id: "manual", label: "Manual review", count: manual.data?.length },
              { id: "score", label: "Score details" },
            ]}
          />
          {tab === "issues" && (
            <TabPanel idPrefix="scan" id="issues">
              <IssuesTable scanId={s.id} />
            </TabPanel>
          )}
          {tab === "pages" && (
            <TabPanel idPrefix="scan" id="pages">
              <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">Scanned pages</caption>
                  <thead className="bg-slate-50 text-slate-700">
                    <tr>
                      <th scope="col" className="px-3 py-2 font-medium">Page</th>
                      <th scope="col" className="px-3 py-2 font-medium">Status</th>
                      <th scope="col" className="px-3 py-2 font-medium">Score</th>
                      <th scope="col" className="px-3 py-2 font-medium">Violations</th>
                      <th scope="col" className="px-3 py-2 font-medium">Needs review</th>
                      <th scope="col" className="px-3 py-2 font-medium">Passed rules</th>
                      <th scope="col" className="px-3 py-2 font-medium">Load time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pages.data?.map((p) => (
                      <tr key={p.id} className="border-t border-slate-100 align-top">
                        <td className="max-w-md px-3 py-2">
                          <span className="block font-medium">{p.title || "(no title)"}</span>
                          <span className="block break-all text-xs text-slate-700">{p.final_url || p.url}</span>
                          {p.error && <span className="block text-xs text-red-800">{p.error}</span>}
                        </td>
                        <td className="px-3 py-2">{p.status}{p.http_status ? ` (${p.http_status})` : ""}</td>
                        <td className="px-3 py-2">{p.score ?? "—"}</td>
                        <td className="px-3 py-2">{p.violations_count}</td>
                        <td className="px-3 py-2">{p.needs_review_count}</td>
                        <td className="px-3 py-2">{p.passed_rules.length}</td>
                        <td className="px-3 py-2">{p.load_time_ms ? `${(p.load_time_ms / 1000).toFixed(1)} s` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </TabPanel>
          )}
          {tab === "manual" && (
            <TabPanel idPrefix="scan" id="manual">
              <Alert tone="info" className="mb-4">These WCAG 2.2 success criteria cannot be fully verified by automated tools. Test them manually (keyboard, screen reader, zoom) before drawing conclusions.</Alert>
              <ul className="grid gap-3 md:grid-cols-2">
                {manual.data?.map((m) => (
                  <li key={m.criterion + m.title} className="rounded-xl border border-slate-200 bg-white p-4">
                    <p className="text-xs font-semibold text-navy-700">{m.criterion} {m.name} (Level {m.level})</p>
                    <h3 className="mt-1 font-semibold text-navy-900">{m.title}</h3>
                    <p className="mt-1 text-sm text-slate-800">{m.how}</p>
                  </li>
                ))}
              </ul>
            </TabPanel>
          )}
          {tab === "score" && (
            <TabPanel idPrefix="scan" id="score">
              <p className="mb-3 text-sm text-slate-800">Each failed rule deducts points from its page's 100 according to its severity; the scan score is the average page score. Needs-review items and manual checks do not change the score.</p>
              {pages.data?.filter((p) => p.status === "ok").map((p) => (
                <Card key={p.id} className="mb-3">
                  <h3 className="font-semibold">{p.title || p.url} — {p.score}</h3>
                  {(p.page_metadata.score_breakdown ?? []).length === 0 ? (
                    <p className="text-sm text-slate-700">No deductions: no rule failed on this page.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="mt-2 w-full text-left text-sm">
                        <caption className="sr-only">Score deductions for {p.url}</caption>
                        <thead className="text-slate-700"><tr><th scope="col" className="py-1 pr-3 font-medium">Rule</th><th scope="col" className="py-1 pr-3 font-medium">Severity</th><th scope="col" className="py-1 pr-3 font-medium">Elements</th><th scope="col" className="py-1 font-medium">Deduction</th></tr></thead>
                        <tbody>
                          {p.page_metadata.score_breakdown!.map((b) => (
                            <tr key={b.rule_id} className="border-t border-slate-100"><td className="py-1 pr-3"><code>{b.rule_id}</code></td><td className="py-1 pr-3 capitalize">{b.impact}</td><td className="py-1 pr-3">{b.nodes}</td><td className="py-1">−{b.deduction}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Card>
              ))}
              <p className="text-xs text-slate-700">Scanner: {s.scanner_version || "—"}</p>
            </TabPanel>
          )}
        </>
      )}

      <Dialog open={methodOpen} onOpenChange={setMethodOpen} title="How the score is calculated" wide>
        {method.data && (
          <div className="space-y-3 text-sm text-slate-800">
            <p>Every page starts at 100. Each automated rule that fails deducts points by severity:</p>
            <ul className="grid grid-cols-2 gap-1 sm:grid-cols-4">
              {Object.entries(method.data.weights).map(([k, v]) => <li key={k} className="rounded bg-slate-100 px-2 py-1 capitalize">{k}: {v}</li>)}
            </ul>
            <p>Each additional affected element adds 10% of the rule's weight, up to 10 extra elements (so one rule deducts at most twice its weight). The scan score is the average of all successfully scanned pages.</p>
            <pre className="code-block rounded bg-slate-50 p-2 text-xs">{method.data.formula}</pre>
            <Alert tone="warning">{method.data.disclaimer}</Alert>
            <p>
              <Link to={`/scans/${id}`} onClick={() => { setMethodOpen(false); setTab("score"); }} className="font-medium text-navy-800 underline">See this scan's deductions</Link>
            </p>
          </div>
        )}
      </Dialog>
    </>
  );
}
