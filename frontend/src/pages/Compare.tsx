import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, qs } from "../api/client";
import type { Comparison, ComparisonIssue, Paged, Scan, Website } from "../api/types";
import { usePageTitle } from "../components/Layout";
import { Alert, Card, ImpactBadge, PageHeader, SelectField, Spinner, TabPanel, Tabs, Tag } from "../components/ui";
import { formatDate } from "../lib/format";

function IssueList({ items, empty }: { items: ComparisonIssue[]; empty: string }) {
  if (items.length === 0) return <p className="text-sm text-slate-700">{empty}</p>;
  return (
    <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
      {items.map((i) => (
        <li key={i.issue_id} className="flex flex-col gap-1 p-3 text-sm sm:flex-row sm:items-start sm:gap-3">
          <ImpactBadge impact={i.impact} />
          <div className="min-w-0">
            <Link to={`/issues/${i.issue_id}`} className="font-medium text-navy-800 underline">{i.help || i.rule_id}</Link>
            {i.kind === "needs_review" && <span className="ml-2 text-xs text-slate-700">(needs review)</span>}
            <p className="truncate text-xs text-slate-700"><code>{i.selector}</code> · {i.page_url}</p>
          </div>
          <div className="ml-auto flex gap-1">{i.wcag_criteria.length ? i.wcag_criteria.map((c) => <Tag key={c} tone="navy">{c}</Tag>) : <Tag>Best practice</Tag>}</div>
        </li>
      ))}
    </ul>
  );
}

function Delta({ value, invert }: { value: number | null; invert?: boolean }) {
  if (value === null || value === undefined) return <span>—</span>;
  const good = invert ? value < 0 : value > 0;
  const cls = value === 0 ? "text-slate-800" : good ? "text-emerald-800" : "text-red-800";
  return <span className={`font-semibold ${cls}`}>{value > 0 ? "+" : ""}{value}</span>;
}

type Tab = "new" | "resolved" | "remaining" | "changed";

export default function Compare() {
  usePageTitle("Compare scans");
  const [params, setParams] = useSearchParams();
  const base = params.get("base") ?? "";
  const target = params.get("target") ?? "";
  const [websiteId, setWebsiteId] = useState("");
  const [tab, setTab] = useState<Tab>("new");
  const sites = useQuery({ queryKey: ["websites", false], queryFn: () => api<Website[]>("/websites") });
  const scans = useQuery({
    queryKey: ["scans", { website: websiteId, completed: true }],
    queryFn: () => api<Paged<Scan>>(`/scans${qs({ website_id: websiteId, status: "completed", page_size: 50 })}`),
    enabled: !!websiteId,
  });
  const cmp = useQuery({ queryKey: ["compare", base, target], queryFn: () => api<Comparison>(`/scans/${base}/compare/${target}`), enabled: !!base && !!target });
  const setPair = (k: "base" | "target", v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
  };

  return (
    <>
      <PageHeader title="Compare scans" description="See what changed between two completed scans of the same website." />
      <Card className="mb-6">
        <div className="grid gap-4 md:grid-cols-3">
          <SelectField label="Website" value={websiteId} onChange={(e) => setWebsiteId(e.target.value)}>
            <option value="">Choose a website…</option>
            {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </SelectField>
          <SelectField label="Earlier scan (base)" value={base} onChange={(e) => setPair("base", e.target.value)} disabled={!scans.data && !base}>
            <option value="">{base && !scans.data ? "Selected scan" : "Choose a scan…"}</option>
            {base && !scans.data && <option value={base}>Selected scan</option>}
            {scans.data?.items.map((s) => <option key={s.id} value={s.id}>{formatDate(s.created_at)} – score {s.score ?? "—"}</option>)}
          </SelectField>
          <SelectField label="Later scan (target)" value={target} onChange={(e) => setPair("target", e.target.value)} disabled={!scans.data && !target}>
            <option value="">{target && !scans.data ? "Selected scan" : "Choose a scan…"}</option>
            {target && !scans.data && <option value={target}>Selected scan</option>}
            {scans.data?.items.map((s) => <option key={s.id} value={s.id}>{formatDate(s.created_at)} – score {s.score ?? "—"}</option>)}
          </SelectField>
        </div>
      </Card>

      {!base || !target ? (
        <p className="text-slate-700">Choose two completed scans to compare. You can also select scans on a website's scan history.</p>
      ) : cmp.isLoading ? (
        <Spinner label="Comparing scans" />
      ) : cmp.error ? (
        <Alert tone="error">{(cmp.error as Error).message}</Alert>
      ) : cmp.data ? (
        <>
          <p className="mb-4 text-sm text-slate-800">
            Comparing <Link className="font-medium text-navy-800 underline" to={`/scans/${cmp.data.base_scan_id}`}>{formatDate(cmp.data.base_date)}</Link> with{" "}
            <Link className="font-medium text-navy-800 underline" to={`/scans/${cmp.data.target_scan_id}`}>{formatDate(cmp.data.target_date)}</Link>.
          </p>
          <dl className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-6">
            {[
              ["Score", <>{cmp.data.score_base ?? "—"} → {cmp.data.score_target ?? "—"} (<Delta value={cmp.data.score_change} />)</>],
              ["New issues", cmp.data.counts.new],
              ["Resolved issues", cmp.data.counts.resolved],
              ["Remaining", cmp.data.counts.remaining],
              ["Passed checks", <>{cmp.data.passed_checks.target} (<Delta value={cmp.data.passed_checks.change} />)</>],
              ["Needs review", <>{cmp.data.needs_review.target} (<Delta value={cmp.data.needs_review.change} invert />)</>],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-xl border border-slate-200 bg-white p-3">
                <dt className="text-sm text-slate-700">{label}</dt>
                <dd className="mt-1 text-lg font-semibold">{value}</dd>
              </div>
            ))}
          </dl>
          <Card className="mb-6">
            <h2 className="mb-2 font-semibold text-navy-900">Change in violations by severity</h2>
            <ul className="flex flex-wrap gap-4 text-sm">
              {Object.entries(cmp.data.impact_delta).map(([k, v]) => <li key={k} className="capitalize">{k}: <Delta value={v} invert /></li>)}
            </ul>
          </Card>
          <Alert tone="info" className="mb-4">{cmp.data.note}</Alert>
          <Tabs idPrefix="cmp" label="Comparison details" value={tab} onChange={setTab} tabs={[
            { id: "new", label: "New", count: cmp.data.counts.new },
            { id: "resolved", label: "Resolved", count: cmp.data.counts.resolved },
            { id: "remaining", label: "Remaining", count: cmp.data.counts.remaining },
            { id: "changed", label: "Severity changes", count: cmp.data.severity_changes.length },
          ]} />
          <TabPanel idPrefix="cmp" id={tab}>
            {tab === "new" && <IssueList items={cmp.data.new_issues} empty="No new issues." />}
            {tab === "resolved" && <IssueList items={cmp.data.resolved_issues} empty="No issues were resolved." />}
            {tab === "remaining" && <IssueList items={cmp.data.remaining_issues} empty="No issues remain from the earlier scan." />}
            {tab === "changed" && (cmp.data.severity_changes.length === 0 ? <p className="text-sm text-slate-700">No severity changes.</p> : (
              <ul className="space-y-2 text-sm">
                {cmp.data.severity_changes.map((c) => (
                  <li key={c.issue_id}><Link to={`/issues/${c.issue_id}`} className="font-medium text-navy-800 underline">{c.rule_id}</Link>: {c.from} → {c.to} <span className="text-slate-700">({c.selector})</span></li>
                ))}
              </ul>
            ))}
          </TabPanel>
        </>
      ) : null}
    </>
  );
}
