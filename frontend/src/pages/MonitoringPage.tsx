import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, put } from "../api/client";
import type { Monitoring, Website } from "../api/types";
import { usePageTitle } from "../components/Layout";
import { Alert, Button, Card, Checkbox, EmptyState, PageHeader, SelectField, Spinner, TextField } from "../components/ui";
import { formatDate } from "../lib/format";

export function MonitoringForm({ website }: { website: Website }) {
  const qc = useQueryClient();
  const cfg = useQuery({ queryKey: ["monitoring", website.id], queryFn: () => api<Monitoring | null>(`/websites/${website.id}/monitoring`) });
  const [enabled, setEnabled] = useState(false);
  const [frequency, setFrequency] = useState("weekly");
  const [mode, setMode] = useState("single");
  const [maxPages, setMaxPages] = useState(5);
  const [maxDepth, setMaxDepth] = useState(1);
  const [notifyComplete, setNotifyComplete] = useState(true);
  const [notifyRegression, setNotifyRegression] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (cfg.data) {
      setEnabled(cfg.data.enabled);
      setFrequency(cfg.data.frequency);
      setMode(cfg.data.scan_config.mode ?? "single");
      setMaxPages(cfg.data.scan_config.max_pages ?? 5);
      setMaxDepth(cfg.data.scan_config.max_depth ?? 1);
      setNotifyComplete(cfg.data.notify_on_complete);
      setNotifyRegression(cfg.data.notify_on_regression);
    }
  }, [cfg.data]);

  const save = useMutation({
    mutationFn: () => put<Monitoring>(`/websites/${website.id}/monitoring`, { enabled, frequency, mode, max_pages: maxPages, max_depth: maxDepth, notify_on_complete: notifyComplete, notify_on_regression: notifyRegression }),
    onSuccess: (m) => {
      setMsg(m.enabled ? `Monitoring enabled. Next scan: ${formatDate(m.next_run_at)}.` : "Monitoring is off. No scheduled scans will run.");
      qc.invalidateQueries({ queryKey: ["monitoring"] });
      qc.invalidateQueries({ queryKey: ["website", website.id] });
      qc.invalidateQueries({ queryKey: ["websites"] });
    },
  });

  if (cfg.isLoading) return <Spinner />;
  return (
    <form className="flex flex-col gap-4" onSubmit={(e: FormEvent) => { e.preventDefault(); setMsg(null); save.mutate(); }}>
      <Checkbox label={`Scan ${website.name} automatically`} description="Scheduled scans run only while this is enabled. You can turn it off at any time." checked={enabled} onChange={(e) => setEnabled(e.target.checked)} disabled={website.is_archived} />
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField label="Frequency" value={frequency} onChange={(e) => setFrequency(e.target.value)} disabled={!enabled}>
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly (every 30 days)</option>
        </SelectField>
        <SelectField label="Scan type" value={mode} onChange={(e) => setMode(e.target.value)} disabled={!enabled}>
          <option value="single">Single page</option>
          <option value="crawl">Limited crawl</option>
        </SelectField>
        {mode === "crawl" && (
          <>
            <TextField label="Maximum pages" type="number" min={1} max={50} value={maxPages} disabled={!enabled} onChange={(e) => setMaxPages(Math.min(50, Math.max(1, Number(e.target.value) || 1)))} />
            <TextField label="Maximum depth" type="number" min={0} max={5} value={maxDepth} disabled={!enabled} onChange={(e) => setMaxDepth(Math.min(5, Math.max(0, Number(e.target.value) || 0)))} />
          </>
        )}
      </div>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-slate-900">Notifications for scheduled scans</legend>
        <Checkbox label="When a scan completes" checked={notifyComplete} onChange={(e) => setNotifyComplete(e.target.checked)} />
        <Checkbox label="When new violations or regressions are detected" checked={notifyRegression} onChange={(e) => setNotifyRegression(e.target.checked)} />
      </fieldset>
      {cfg.data?.enabled && <p className="text-sm text-slate-700">Next scheduled scan: {formatDate(cfg.data.next_run_at)} · Last run: {formatDate(cfg.data.last_run_at)}</p>}
      <div><Button type="submit" loading={save.isPending}>Save monitoring settings</Button></div>
      {msg && <Alert tone="success" live>{msg}</Alert>}
      {save.error && <Alert tone="error" live>{(save.error as Error).message}</Alert>}
    </form>
  );
}

export default function MonitoringPage() {
  usePageTitle("Monitoring");
  const sites = useQuery({ queryKey: ["websites", false], queryFn: () => api<Website[]>("/websites") });
  const configs = useQuery({ queryKey: ["monitoring"], queryFn: () => api<Monitoring[]>("/monitoring") });
  const [selected, setSelected] = useState("");
  const site = sites.data?.find((s) => s.id === selected);
  return (
    <>
      <PageHeader title="Monitoring" description="Schedule recurring scans and get notified about regressions. Nothing runs on a schedule unless you enable it." />
      {sites.isLoading ? <Spinner /> : sites.data?.length === 0 ? (
        <EmptyState title="No websites to monitor"><Link to="/websites?add=1" className="font-medium text-navy-800 underline">Add a website</Link> first.</EmptyState>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card aria-labelledby="mon-list-h">
            <h2 id="mon-list-h" className="mb-3 font-semibold text-navy-900">Monitored websites</h2>
            {(configs.data ?? []).filter((c) => c.enabled).length === 0 ? (
              <p className="text-sm text-slate-700">No website has scheduled scans.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {configs.data!.filter((c) => c.enabled).map((c) => (
                  <li key={c.id} className="py-2 text-sm">
                    <Link to={`/websites/${c.website_id}`} className="font-medium text-navy-800 underline">{c.website_name}</Link>
                    <p className="text-slate-700">{c.frequency[0].toUpperCase() + c.frequency.slice(1)} · {c.scan_config.mode === "crawl" ? `crawl up to ${c.scan_config.max_pages} pages` : "single page"} · next {formatDate(c.next_run_at)}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card aria-labelledby="mon-edit-h">
            <h2 id="mon-edit-h" className="mb-3 font-semibold text-navy-900">Configure a website</h2>
            <SelectField label="Website" value={selected} onChange={(e) => setSelected(e.target.value)}>
              <option value="">Choose a website…</option>
              {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </SelectField>
            {site && <div className="mt-4"><MonitoringForm key={site.id} website={site} /></div>}
          </Card>
        </div>
      )}
    </>
  );
}
