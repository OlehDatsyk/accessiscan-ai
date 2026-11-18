import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, GitCompare, Pencil, ScanSearch, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, del, patch, qs } from "../api/client";
import type { Paged, Scan, Website } from "../api/types";
import { GroupedBarChart, TrendChart } from "../components/charts";
import { usePageTitle } from "../components/Layout";
import { MonitoringForm } from "./MonitoringPage";
import { Alert, Button, ButtonLink, Card, ConfirmDialog, Dialog, PageHeader, Pagination, ScoreRing, Spinner, StatusBadge, TabPanel, Tabs } from "../components/ui";
import { formatDate } from "../lib/format";
import { WebsiteForm } from "./Websites";

interface WebsiteAnalytics {
  trend: { scan_id: string; date: string; score: number | null; violations: number; needs_review: number; critical: number; serious: number; moderate: number; minor: number; new: number | null; resolved: number | null }[];
}

type Tab = "history" | "analytics" | "monitoring";

export default function WebsiteDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("history");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const site = useQuery({ queryKey: ["website", id], queryFn: () => api<Website>(`/websites/${id}`) });
  usePageTitle(site.data?.name ?? "Website");
  const scans = useQuery({
    queryKey: ["scans", { website: id, page }],
    queryFn: () => api<Paged<Scan>>(`/scans${qs({ website_id: id, page, page_size: 10 })}`),
    refetchInterval: (q) => (q.state.data?.items.some((s) => s.status === "queued" || s.status === "running") ? 3000 : false),
  });
  const analytics = useQuery({ queryKey: ["website-analytics", id], queryFn: () => api<WebsiteAnalytics>(`/websites/${id}/analytics`), enabled: tab === "analytics" });

  const archive = useMutation({
    mutationFn: (archived: boolean) => patch<Website>(`/websites/${id}`, { is_archived: archived }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website", id] });
      qc.invalidateQueries({ queryKey: ["websites"] });
    },
  });
  const remove = useMutation({
    mutationFn: () => del(`/websites/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["websites"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      navigate("/websites");
    },
  });

  if (site.isLoading) return <Spinner />;
  if (site.error) return <Alert tone="error" title="Website not found">{(site.error as Error).message}</Alert>;
  const w = site.data!;
  const completed = scans.data?.items.filter((s) => s.status === "completed") ?? [];
  const toggle = (sid: string) => setSelected((cur) => (cur.includes(sid) ? cur.filter((x) => x !== sid) : [...cur, sid].slice(-2)));

  return (
    <>
      <PageHeader
        title={w.name}
        description={<a href={w.url} target="_blank" rel="noopener noreferrer" className="text-navy-800 underline">{w.url}<span className="sr-only"> (opens in a new tab)</span></a>}
        actions={
          <>
            {!w.is_archived && <ButtonLink to={`/scans/new?website=${w.id}`}><ScanSearch className="h-4 w-4" aria-hidden="true" />New scan</ButtonLink>}
            <Button variant="secondary" onClick={() => setEditing(true)} icon={<Pencil className="h-4 w-4" aria-hidden="true" />}>Edit</Button>
            <Button variant="secondary" loading={archive.isPending} onClick={() => archive.mutate(!w.is_archived)} icon={<Archive className="h-4 w-4" aria-hidden="true" />}>
              {w.is_archived ? "Restore" : "Archive"}
            </Button>
            <Button variant="danger" onClick={() => setConfirmDelete(true)} icon={<Trash2 className="h-4 w-4" aria-hidden="true" />}>Delete</Button>
          </>
        }
      />
      {w.is_archived && <Alert tone="warning" className="mb-4" title="This website is archived">Restore it to run new scans or enable monitoring.</Alert>}
      {remove.error && <Alert tone="error" className="mb-4" live>{(remove.error as Error).message}</Alert>}
      {w.description && <p className="mb-4 max-w-3xl text-slate-700">{w.description}</p>}

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Card className="flex items-center gap-4">
          <ScoreRing score={w.latest_score} size={72} />
          <div>
            <p className="text-sm text-slate-700">Latest score</p>
            <p className="text-xs text-slate-700">Indicator of automatically detected issues, not a compliance rating.</p>
          </div>
        </Card>
        <Card><p className="text-sm text-slate-700">Open violations (latest scan)</p><p className="mt-1 text-2xl font-semibold">{w.open_violations}</p></Card>
        <Card><p className="text-sm text-slate-700">Scans</p><p className="mt-1 text-2xl font-semibold">{w.scan_count}</p><p className="text-xs text-slate-700">Monitoring {w.monitoring_enabled ? "enabled" : "off"}</p></Card>
      </div>

      <Tabs idPrefix="site" label="Website sections" value={tab} onChange={setTab} tabs={[{ id: "history", label: "Scan history" }, { id: "analytics", label: "Analytics" }, { id: "monitoring", label: "Monitoring" }]} />

      {tab === "history" && (
        <TabPanel idPrefix="site" id="history">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <p className="text-sm text-slate-700">Select two completed scans to compare them.</p>
            <ButtonLink
              to={selected.length === 2 ? `/compare?base=${selected[0]}&target=${selected[1]}` : "#"}
              variant="secondary"
              size="sm"
              aria-disabled={selected.length !== 2}
              onClick={(e) => selected.length !== 2 && e.preventDefault()}
              className={selected.length !== 2 ? "pointer-events-auto opacity-60" : undefined}
            >
              <GitCompare className="h-4 w-4" aria-hidden="true" />Compare selected ({selected.length}/2)
            </ButtonLink>
          </div>
          {scans.isLoading ? <Spinner /> : scans.data && scans.data.items.length === 0 ? (
            <p className="text-slate-700">No scans yet. <Link to={`/scans/new?website=${w.id}`} className="font-medium text-navy-800 underline">Run the first scan</Link>.</p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Scan history for {w.name}</caption>
                <thead className="bg-slate-50 text-slate-700">
                  <tr>
                    <th scope="col" className="px-3 py-2 font-medium"><span className="sr-only">Select for comparison</span></th>
                    <th scope="col" className="px-3 py-2 font-medium">Date</th>
                    <th scope="col" className="px-3 py-2 font-medium">Status</th>
                    <th scope="col" className="px-3 py-2 font-medium">Mode</th>
                    <th scope="col" className="px-3 py-2 font-medium">Pages</th>
                    <th scope="col" className="px-3 py-2 font-medium">Score</th>
                    <th scope="col" className="px-3 py-2 font-medium">Violations</th>
                  </tr>
                </thead>
                <tbody>
                  {scans.data?.items.map((s) => (
                    <tr key={s.id} className="border-t border-slate-100">
                      <td className="px-3 py-2">
                        {s.status === "completed" && (
                          <input type="checkbox" className="h-4 w-4 accent-navy-800" checked={selected.includes(s.id)} onChange={() => toggle(s.id)} aria-label={`Compare scan from ${formatDate(s.created_at)}`} />
                        )}
                      </td>
                      <td className="px-3 py-2"><Link to={`/scans/${s.id}`} className="font-medium text-navy-800 underline">{formatDate(s.created_at)}</Link></td>
                      <td className="px-3 py-2"><StatusBadge status={s.status} /></td>
                      <td className="px-3 py-2 capitalize">{s.mode}{s.trigger === "schedule" ? " (scheduled)" : ""}</td>
                      <td className="px-3 py-2">{s.summary.pages_scanned ?? s.pages_done}</td>
                      <td className="px-3 py-2">{s.score ?? "—"}</td>
                      <td className="px-3 py-2">{s.summary.violations ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {scans.data && <Pagination page={page} pageSize={10} total={scans.data.total} onPage={setPage} />}
          {completed.length < 2 && scans.data && scans.data.total > 0 && <p className="mt-2 text-xs text-slate-700">At least two completed scans are needed for a comparison.</p>}
        </TabPanel>
      )}

      {tab === "analytics" && (
        <TabPanel idPrefix="site" id="analytics">
          {analytics.isLoading ? <Spinner /> : (
            <div className="grid gap-6 xl:grid-cols-2">
              <TrendChart
                title="Score over time"
                description="Completed scans of this website"
                rows={(analytics.data?.trend ?? []).map((t) => ({ date: formatDate(t.date, false), score: t.score }))}
                lines={[{ key: "score", label: "Score", color: "#1b3563" }]}
                domain={[0, 100]}
              />
              <TrendChart
                title="Violations by severity over time"
                rows={(analytics.data?.trend ?? []).map((t) => ({ date: formatDate(t.date, false), critical: t.critical, serious: t.serious, moderate: t.moderate, minor: t.minor }))}
                lines={[
                  { key: "critical", label: "Critical", color: "#b91c1c" },
                  { key: "serious", label: "Serious", color: "#c2410c" },
                  { key: "moderate", label: "Moderate", color: "#a16207" },
                  { key: "minor", label: "Minor", color: "#475569" },
                ]}
              />
              <GroupedBarChart
                title="New versus resolved violations"
                description="Compared with the previous completed scan"
                rows={(analytics.data?.trend ?? []).filter((t) => t.new !== null).map((t) => ({ date: formatDate(t.date, false), new: t.new ?? 0, resolved: t.resolved ?? 0 }))}
                bars={[{ key: "new", label: "New", color: "#b91c1c" }, { key: "resolved", label: "Resolved", color: "#0d8278" }]}
              />
            </div>
          )}
        </TabPanel>
      )}

      {tab === "monitoring" && (
        <TabPanel idPrefix="site" id="monitoring">
          <Card className="max-w-2xl">
            <MonitoringForm website={w} />
          </Card>
        </TabPanel>
      )}

      <Dialog open={editing} onOpenChange={setEditing} title="Edit website">
        <WebsiteForm initial={w} onDone={() => setEditing(false)} />
      </Dialog>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete ${w.name}?`}
        description="This permanently deletes the website with all of its scans, issues, notes and reports. This cannot be undone. Consider archiving instead."
        confirmLabel="Delete permanently"
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </>
  );
}
