import { useQuery } from "@tanstack/react-query";
import { Radar, ScanSearch } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, qs } from "../api/client";
import type { Paged, Scan } from "../api/types";
import { usePageTitle } from "../components/Layout";
import { Alert, ButtonLink, EmptyState, PageHeader, Pagination, SelectField, Spinner, StatusBadge } from "../components/ui";
import { formatDate } from "../lib/format";

export default function ScansList() {
  usePageTitle("Scan results");
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const { data, isLoading, error } = useQuery({
    queryKey: ["scans", { page, status }],
    queryFn: () => api<Paged<Scan>>(`/scans${qs({ page, page_size: 20, status })}`),
    refetchInterval: (q) => (q.state.data?.items.some((s) => s.status === "queued" || s.status === "running") ? 3000 : false),
  });
  return (
    <>
      <PageHeader title="Scan results" description="All scans across your websites, newest first." actions={<ButtonLink to="/scans/new"><ScanSearch className="h-4 w-4" aria-hidden="true" />New scan</ButtonLink>} />
      <div className="mb-4 max-w-xs">
        <SelectField label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All statuses</option>
          {["queued", "running", "completed", "failed", "cancelled"].map((s) => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
        </SelectField>
      </div>
      {isLoading && <Spinner />}
      {error && <Alert tone="error">{(error as Error).message}</Alert>}
      {data && data.items.length === 0 && (
        <EmptyState icon={<Radar className="h-10 w-10" />} title="No scans found" action={<ButtonLink to="/scans/new">Start a scan</ButtonLink>}>
          Scans you start, and scheduled monitoring scans, appear here.
        </EmptyState>
      )}
      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Scans</caption>
            <thead className="bg-slate-50 text-slate-700">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">Website</th>
                <th scope="col" className="px-3 py-2 font-medium">Date</th>
                <th scope="col" className="px-3 py-2 font-medium">Status</th>
                <th scope="col" className="px-3 py-2 font-medium">Type</th>
                <th scope="col" className="px-3 py-2 font-medium">Score</th>
                <th scope="col" className="px-3 py-2 font-medium">Violations</th>
                <th scope="col" className="px-3 py-2 font-medium">Needs review</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((s) => (
                <tr key={s.id} className="border-t border-slate-100">
                  <td className="px-3 py-2"><Link to={`/scans/${s.id}`} className="font-medium text-navy-800 underline">{s.website_name}</Link></td>
                  <td className="px-3 py-2">{formatDate(s.created_at)}</td>
                  <td className="px-3 py-2"><StatusBadge status={s.status} />{s.status === "failed" && <span className="block max-w-xs truncate text-xs text-red-800" title={s.error_message}>{s.error_message}</span>}</td>
                  <td className="px-3 py-2 capitalize">{s.mode}{s.trigger === "schedule" ? " · scheduled" : ""}</td>
                  <td className="px-3 py-2">{s.score ?? "—"}</td>
                  <td className="px-3 py-2">{s.summary.violations ?? "—"}</td>
                  <td className="px-3 py-2">{s.summary.needs_review ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && <Pagination page={page} pageSize={20} total={data.total} onPage={setPage} />}
    </>
  );
}
