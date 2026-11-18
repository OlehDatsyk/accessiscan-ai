import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, del, downloadReport, post, qs } from "../api/client";
import type { Paged, Report, Scan } from "../api/types";
import { usePageTitle } from "../components/Layout";
import { Alert, Button, Card, ConfirmDialog, EmptyState, PageHeader, SelectField, Spinner } from "../components/ui";
import { formatBytes, formatDate } from "../lib/format";

export default function Reports() {
  usePageTitle("Reports");
  const qc = useQueryClient();
  const [scanId, setScanId] = useState("");
  const [format, setFormat] = useState("pdf");
  const [message, setMessage] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<Report | null>(null);
  const reports = useQuery({ queryKey: ["reports"], queryFn: () => api<Report[]>("/reports") });
  const scans = useQuery({ queryKey: ["scans", { completed: true, all: true }], queryFn: () => api<Paged<Scan>>(`/scans${qs({ status: "completed", page_size: 50 })}`) });
  const scanName = new Map((scans.data?.items ?? []).map((s) => [s.id, `${s.website_name} – ${formatDate(s.created_at)}`]));
  const create = useMutation({
    mutationFn: () => post<Report>("/reports", { scan_id: scanId, format }),
    onSuccess: async (r) => {
      qc.invalidateQueries({ queryKey: ["reports"] });
      setMessage(`Generated ${r.filename}.`);
      await downloadReport(r.id, r.filename);
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => del(`/reports/${id}`),
    onSuccess: () => {
      setToDelete(null);
      setMessage("Report deleted.");
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
  const download = useMutation({ mutationFn: (r: Report) => downloadReport(r.id, r.filename) });

  return (
    <>
      <PageHeader title="Reports" description="PDF, CSV and Word reports of completed scans. Reports are automated assessments, not legal certification." />
      <Card className="mb-6">
        <form className="grid gap-4 md:grid-cols-[2fr_1fr_auto] md:items-end" onSubmit={(e: FormEvent) => { e.preventDefault(); setMessage(null); if (scanId) create.mutate(); }}>
          <SelectField label="Completed scan" required value={scanId} onChange={(e) => setScanId(e.target.value)}>
            <option value="">Choose a scan…</option>
            {scans.data?.items.map((s) => <option key={s.id} value={s.id}>{s.website_name} – {formatDate(s.created_at)} (score {s.score ?? "—"})</option>)}
          </SelectField>
          <SelectField label="Format" value={format} onChange={(e) => setFormat(e.target.value)}>
            <option value="pdf">PDF report</option>
            <option value="csv">CSV (all issues)</option>
            <option value="docx">Word document (DOCX)</option>
          </SelectField>
          <Button type="submit" loading={create.isPending} disabled={!scanId}>Generate report</Button>
        </form>
        {create.error && <Alert tone="error" live className="mt-3">{(create.error as Error).message}</Alert>}
        {message && <Alert tone="success" live className="mt-3">{message}</Alert>}
      </Card>

      {reports.isLoading ? <Spinner /> : reports.data && reports.data.length === 0 ? (
        <EmptyState icon={<FileText className="h-10 w-10" />} title="No reports yet">Generate a report from a completed scan above or from the scan results page.</EmptyState>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Generated reports</caption>
            <thead className="bg-slate-50 text-slate-700">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">File</th>
                <th scope="col" className="px-3 py-2 font-medium">Scan</th>
                <th scope="col" className="px-3 py-2 font-medium">Format</th>
                <th scope="col" className="px-3 py-2 font-medium">Size</th>
                <th scope="col" className="px-3 py-2 font-medium">Created</th>
                <th scope="col" className="px-3 py-2 font-medium"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {reports.data?.map((r) => (
                <tr key={r.id} className="border-t border-slate-100">
                  <td className="px-3 py-2 font-medium">{r.filename}</td>
                  <td className="px-3 py-2"><Link to={`/scans/${r.scan_id}`} className="text-navy-800 underline">{scanName.get(r.scan_id) ?? "View scan"}</Link></td>
                  <td className="px-3 py-2 uppercase">{r.format}</td>
                  <td className="px-3 py-2">{formatBytes(r.size_bytes)}</td>
                  <td className="px-3 py-2">{formatDate(r.created_at)}</td>
                  <td className="px-3 py-2">
                    <div className="flex gap-1">
                      <Button size="sm" variant="secondary" onClick={() => download.mutate(r)} icon={<Download className="h-4 w-4" aria-hidden="true" />}>Download<span className="sr-only"> {r.filename}</span></Button>
                      <Button size="sm" variant="ghost" onClick={() => setToDelete(r)} aria-label={`Delete ${r.filename}`}><Trash2 className="h-4 w-4" aria-hidden="true" /></Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ConfirmDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)} title="Delete report?" description={`${toDelete?.filename ?? ""} will be permanently deleted. You can generate it again from the scan.`} confirmLabel="Delete report" loading={remove.isPending} onConfirm={() => toDelete && remove.mutate(toDelete.id)} />
    </>
  );
}
