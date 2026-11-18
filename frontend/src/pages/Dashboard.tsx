import { useQuery } from "@tanstack/react-query";
import { AlertOctagon, CheckCheck, FileText, Gauge, Globe, ListChecks, Plus, ScanSearch } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Impact } from "../api/types";
import { SeverityBarChart, SimpleBarChart } from "../components/charts";
import { usePageTitle } from "../components/Layout";
import { Alert, ButtonLink, Card, EmptyState, ScoreRing, Spinner, StatCard, StatusBadge } from "../components/ui";
import { formatDate, relativeTime } from "../lib/format";

interface DashboardData {
  websites: number;
  total_scans: number;
  issues_detected: number;
  critical_issues: number;
  by_impact: Record<Impact, number>;
  needs_review: number;
  fixed_between_scans: number;
  average_score: number | null;
  scored_websites: number;
  recent_scans: { id: string; status: string; score: number | null; created_at: string; mode: string; trigger: string; website_name: string; violations: number | null }[];
  attention: { website_id: string; name: string; url: string; score: number | null; critical: number; new_violations: number; scan_id: string }[];
  scan_activity: { date: string; scans: number }[];
  latest_reports: { id: string; filename: string; format: string; created_at: string; scan_id: string }[];
}

export default function Dashboard() {
  usePageTitle("Dashboard");
  const { data, isLoading, error } = useQuery({ queryKey: ["dashboard"], queryFn: () => api<DashboardData>("/dashboard"), refetchInterval: 20_000 });

  if (isLoading) return <Spinner label="Loading dashboard" />;
  if (error) return <Alert tone="error" title="Could not load the dashboard">{(error as Error).message}</Alert>;
  if (!data) return null;

  const header = (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-navy-900">Dashboard</h1>
        <p className="mt-1 text-slate-700">Accessibility overview across your websites, calculated from your stored scan results.</p>
      </div>
      <div className="flex gap-2">
        <ButtonLink to="/websites?add=1" variant="secondary"><Plus className="h-4 w-4" aria-hidden="true" />Add website</ButtonLink>
        <ButtonLink to="/scans/new"><ScanSearch className="h-4 w-4" aria-hidden="true" />New scan</ButtonLink>
      </div>
    </div>
  );

  if (data.websites === 0) {
    return (
      <>
        {header}
        <EmptyState
          icon={<Globe className="h-10 w-10" />}
          title="Add your first website"
          action={<ButtonLink to="/websites?add=1"><Plus className="h-4 w-4" aria-hidden="true" />Add a website</ButtonLink>}
        >
          Add a website you own or are responsible for, then run a scan. AccessiScan loads the page in a real browser and checks it against WCAG 2.2 A/AA rules with axe-core.
        </EmptyState>
      </>
    );
  }

  return (
    <>
      {header}
      <h2 className="sr-only">Key figures</h2>
      <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Websites monitored" value={data.websites} icon={<Globe className="h-4 w-4" />} hint={`${data.scored_websites} with a completed scan`} />
        <StatCard label="Total scans" value={data.total_scans} icon={<ScanSearch className="h-4 w-4" />} tone="teal" />
        <StatCard label="Average score" value={data.average_score ?? "—"} icon={<Gauge className="h-4 w-4" />} hint="Latest completed scan per website. Not a compliance rating." />
        <StatCard label="Issues detected" value={data.issues_detected} icon={<ListChecks className="h-4 w-4" />} tone="amber" hint={`${data.needs_review} more need manual review`} />
        <StatCard label="Critical issues" value={data.critical_issues} icon={<AlertOctagon className="h-4 w-4" />} tone="red" hint="Elements with critical impact" />
        <StatCard label="Fixed between scans" value={data.fixed_between_scans} icon={<CheckCheck className="h-4 w-4" />} tone="teal" hint="Not detected again in the latest re-scan" />
      </dl>

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <SeverityBarChart data={data.by_impact} title="Issues by severity" />
        <SimpleBarChart title="Scan activity" description="Scans started per day (last 30 days)" rows={data.scan_activity} x="date" y="scans" xLabel="Date" yLabel="Scans" color="#0d8278" />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2" aria-labelledby="recent-h">
          <div className="mb-3 flex items-center justify-between">
            <h2 id="recent-h" className="font-semibold text-navy-900">Recent scan activity</h2>
            <Link to="/scans" className="text-sm font-medium text-navy-800 underline">All scans</Link>
          </div>
          {data.recent_scans.length === 0 ? (
            <p className="text-slate-700">No scans yet. <Link to="/scans/new" className="font-medium text-navy-800 underline">Start your first scan</Link>.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Most recent scans</caption>
                <thead className="text-slate-700">
                  <tr>
                    <th scope="col" className="py-2 pr-3 font-medium">Website</th>
                    <th scope="col" className="py-2 pr-3 font-medium">Status</th>
                    <th scope="col" className="py-2 pr-3 font-medium">Score</th>
                    <th scope="col" className="py-2 pr-3 font-medium">Violations</th>
                    <th scope="col" className="py-2 font-medium">Started</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_scans.map((s) => (
                    <tr key={s.id} className="border-t border-slate-100">
                      <td className="py-2 pr-3">
                        <Link to={`/scans/${s.id}`} className="font-medium text-navy-800 underline">{s.website_name}</Link>
                        {s.trigger === "schedule" && <span className="ml-1 text-xs text-slate-700">(scheduled)</span>}
                      </td>
                      <td className="py-2 pr-3"><StatusBadge status={s.status} /></td>
                      <td className="py-2 pr-3">{s.score ?? "—"}</td>
                      <td className="py-2 pr-3">{s.violations ?? "—"}</td>
                      <td className="py-2"><time dateTime={s.created_at} title={formatDate(s.created_at)}>{relativeTime(s.created_at)}</time></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card aria-labelledby="attention-h">
          <h2 id="attention-h" className="mb-3 font-semibold text-navy-900">Websites requiring attention</h2>
          {data.attention.length === 0 ? (
            <p className="text-slate-700">No website currently has critical issues, new violations or a score below 70.</p>
          ) : (
            <ul className="space-y-3">
              {data.attention.map((a) => (
                <li key={a.website_id} className="flex items-center gap-3">
                  <ScoreRing score={a.score} size={48} />
                  <div className="min-w-0">
                    <Link to={`/scans/${a.scan_id}`} className="block truncate font-medium text-navy-800 underline">{a.name}</Link>
                    <p className="text-xs text-slate-700">
                      {a.critical} critical{a.new_violations ? ` · ${a.new_violations} new since last scan` : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <h2 className="mb-2 mt-6 font-semibold text-navy-900">Latest reports</h2>
          {data.latest_reports.length === 0 ? (
            <p className="text-sm text-slate-700">No reports generated yet.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {data.latest_reports.map((r) => (
                <li key={r.id} className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-slate-600" aria-hidden="true" />
                  <Link to="/reports" className="truncate text-navy-800 underline">{r.filename}</Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
