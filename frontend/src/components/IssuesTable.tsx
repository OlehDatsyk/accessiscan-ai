import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import { api, post, qs } from "../api/client";
import { IMPACTS, type Facets, type Issue, type Paged } from "../api/types";
import { CATEGORY_LABELS, IMPACT_LABEL, STATUS_LABEL } from "../lib/format";
import { Alert, Button, ImpactBadge, Pagination, SelectField, Spinner, StatusBadge, Tag, TextField } from "./ui";

export interface IssueFilters {
  impact: string[];
  kind: string;
  category: string;
  wcag: string;
  status: string;
  q: string;
}

const EMPTY: IssueFilters = { impact: [], kind: "", category: "", wcag: "", status: "", q: "" };

export function IssuesTable({ scanId, websiteId, initial }: { scanId?: string; websiteId?: string; initial?: Partial<IssueFilters> }) {
  const [filters, setFilters] = useState<IssueFilters>({ ...EMPTY, ...initial });
  const [search, setSearch] = useState(filters.q);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const [bulkMessage, setBulkMessage] = useState<string | null>(null);
  const qc = useQueryClient();
  const groupId = useId();
  const pageSize = 25;

  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => (f.q === search ? f : { ...f, q: search })), 350);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => {
    setPage(1);
    setSelected([]);
  }, [filters]);

  const base = { scan_id: scanId, website_id: websiteId };
  const facets = useQuery({ queryKey: ["facets", base], queryFn: () => api<Facets>(`/issues/facets${qs(base)}`) });
  const issues = useQuery({
    queryKey: ["issues", base, filters, page],
    queryFn: () =>
      api<Paged<Issue>>(
        `/issues${qs({ ...base, impact: filters.impact, kind: filters.kind, category: filters.category, wcag: filters.wcag, status: filters.status ? [filters.status] : undefined, q: filters.q, page, page_size: pageSize })}`,
      ),
    placeholderData: (prev) => prev,
  });
  const bulk = useMutation({
    mutationFn: (status: string) => post<{ updated: number }>("/issues/bulk-status", { issue_ids: selected, status, reason: "" }),
    onSuccess: (r, status) => {
      setBulkMessage(`${r.updated} issue${r.updated === 1 ? "" : "s"} marked as ${STATUS_LABEL[status].toLowerCase()}.`);
      setSelected([]);
      qc.invalidateQueries({ queryKey: ["issues"] });
      qc.invalidateQueries({ queryKey: ["facets"] });
    },
  });

  const set = <K extends keyof IssueFilters>(k: K, v: IssueFilters[K]) => setFilters((f) => ({ ...f, [k]: v }));
  const toggleImpact = (i: string) => set("impact", filters.impact.includes(i) ? filters.impact.filter((x) => x !== i) : [...filters.impact, i]);
  const f = facets.data;
  const items = issues.data?.items ?? [];
  const allSelected = items.length > 0 && items.every((i) => selected.includes(i.id));
  const active = JSON.stringify(filters) !== JSON.stringify(EMPTY);

  return (
    <div>
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="sr-only">Filters</h2>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <TextField label="Search" type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Rule, text, selector or URL" />
          <SelectField label="Type" value={filters.kind} onChange={(e) => set("kind", e.target.value)}>
            <option value="">All types</option>
            <option value="violation">Violations ({f?.kind.violation ?? 0})</option>
            <option value="needs_review">Needs review ({f?.kind.needs_review ?? 0})</option>
          </SelectField>
          <SelectField label="Category" value={filters.category} onChange={(e) => set("category", e.target.value)}>
            <option value="">All categories</option>
            {Object.entries(f?.category ?? {}).map(([k, n]) => (
              <option key={k} value={k}>{CATEGORY_LABELS[k] ?? k} ({n})</option>
            ))}
          </SelectField>
          <SelectField label="WCAG criterion" value={filters.wcag} onChange={(e) => set("wcag", e.target.value)}>
            <option value="">All criteria</option>
            {Object.entries(f?.wcag ?? {}).map(([k, n]) => (
              <option key={k} value={k}>{k} ({n})</option>
            ))}
          </SelectField>
          <SelectField label="Status" value={filters.status} onChange={(e) => set("status", e.target.value)}>
            <option value="">All statuses</option>
            {["open", "in_progress", "marked_fixed", "ignored"].map((s) => (
              <option key={s} value={s}>{STATUS_LABEL[s]} ({f?.status[s] ?? 0})</option>
            ))}
          </SelectField>
        </div>
        <fieldset className="mt-4">
          <legend className="text-sm font-medium text-slate-900">Severity</legend>
          <div className="mt-1 flex flex-wrap gap-3">
            {IMPACTS.map((i) => (
              <label key={i} className="flex items-center gap-1.5 text-sm">
                <input type="checkbox" className="h-4 w-4 accent-navy-800" checked={filters.impact.includes(i)} onChange={() => toggleImpact(i)} />
                {IMPACT_LABEL[i]} <span className="text-slate-700">({f?.impact[i] ?? 0})</span>
              </label>
            ))}
            {active && (
              <Button variant="ghost" size="sm" onClick={() => { setFilters(EMPTY); setSearch(""); }}>Clear filters</Button>
            )}
          </div>
        </fieldset>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-700" role="status" aria-live="polite">
          {issues.data ? `${issues.data.total} issue${issues.data.total === 1 ? "" : "s"} found` : ""}
        </p>
        {selected.length > 0 && (
          <div className="flex flex-wrap items-center gap-2" role="group" aria-labelledby={`${groupId}-bulk`}>
            <span id={`${groupId}-bulk`} className="text-sm font-medium">{selected.length} selected:</span>
            <Button size="sm" variant="secondary" onClick={() => bulk.mutate("in_progress")} loading={bulk.isPending}>Mark in progress</Button>
            <Button size="sm" variant="secondary" onClick={() => bulk.mutate("marked_fixed")} loading={bulk.isPending}>Mark fixed</Button>
            <Button size="sm" variant="secondary" onClick={() => bulk.mutate("open")} loading={bulk.isPending}>Reopen</Button>
          </div>
        )}
      </div>
      {bulkMessage && <Alert tone="success" live className="mt-2">{bulkMessage} Ignoring issues requires a reason and is done on each issue's page. Fixes marked here are not verified until a re-scan.</Alert>}
      {issues.error && <Alert tone="error" className="mt-2">{(issues.error as Error).message}</Alert>}
      {issues.isLoading ? (
        <Spinner label="Loading issues" />
      ) : items.length === 0 ? (
        <p className="mt-4 rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center text-slate-700">
          {active ? "No issues match these filters." : "No issues were detected. Automated testing cannot find every barrier, so complete the manual review checklist."}
        </p>
      ) : (
        <div className="mt-2 overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Accessibility issues, sorted by severity</caption>
            <thead className="bg-slate-50 text-slate-700">
              <tr>
                <th scope="col" className="px-3 py-2">
                  <input type="checkbox" className="h-4 w-4 accent-navy-800" checked={allSelected} onChange={() => setSelected(allSelected ? [] : items.map((i) => i.id))} aria-label="Select all issues on this page" />
                </th>
                <th scope="col" className="px-3 py-2 font-medium">Severity</th>
                <th scope="col" className="px-3 py-2 font-medium">Issue</th>
                <th scope="col" className="px-3 py-2 font-medium">WCAG</th>
                <th scope="col" className="px-3 py-2 font-medium">Element</th>
                <th scope="col" className="px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.id} className="border-t border-slate-100 align-top">
                  <td className="px-3 py-2">
                    <input type="checkbox" className="h-4 w-4 accent-navy-800" checked={selected.includes(i.id)} onChange={() => setSelected((s) => (s.includes(i.id) ? s.filter((x) => x !== i.id) : [...s, i.id]))} aria-label={`Select issue: ${i.help}`} />
                  </td>
                  <td className="px-3 py-2">
                    <ImpactBadge impact={i.impact} />
                    {i.kind === "needs_review" && <span className="mt-1 block text-xs text-slate-700">Needs review</span>}
                  </td>
                  <td className="max-w-md px-3 py-2">
                    <Link to={`/issues/${i.id}`} className="font-medium text-navy-800 underline">{i.help || i.rule_id}</Link>
                    <span className="block text-xs text-slate-700">{i.rule_id} · {CATEGORY_LABELS[i.category] ?? i.category}</span>
                    {i.regressed && <span className="mt-1 block text-xs font-medium text-red-800">Previously marked fixed – detected again</span>}
                  </td>
                  <td className="px-3 py-2">
                    {i.wcag_criteria.length ? (
                      <div className="flex flex-wrap gap-1">{i.wcag_criteria.map((c) => <Tag key={c} tone="navy">{c}</Tag>)}<span className="text-xs text-slate-700">{i.wcag_level}</span></div>
                    ) : (
                      <Tag>Best practice</Tag>
                    )}
                  </td>
                  <td className="max-w-xs px-3 py-2">
                    <code className="block truncate text-xs text-slate-800" title={i.selector}>{i.selector}</code>
                    <span className="block truncate text-xs text-slate-700" title={i.page_url}>{i.page_url}</span>
                  </td>
                  <td className="px-3 py-2"><StatusBadge status={i.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {issues.data && <Pagination page={page} pageSize={pageSize} total={issues.data.total} onPage={setPage} />}
    </div>
  );
}
