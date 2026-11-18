import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Globe, Plus, ScanSearch } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { api, patch, post, qs } from "../api/client";
import type { Website } from "../api/types";
import { usePageTitle } from "../components/Layout";
import { Alert, Button, ButtonLink, Checkbox, Dialog, EmptyState, PageHeader, ScoreRing, Spinner, StatusBadge, TextArea, TextField } from "../components/ui";
import { relativeTime } from "../lib/format";

const schema = z.object({
  name: z.string().trim().min(1, "Enter a name").max(120, "Use at most 120 characters"),
  url: z
    .string()
    .trim()
    .min(1, "Enter the website URL")
    .max(2048)
    .refine((v) => {
      try {
        const u = new URL(/^[a-z]+:\/\//i.test(v) ? v : `https://${v}`);
        return ["http:", "https:"].includes(u.protocol) && !!u.hostname;
      } catch {
        return false;
      }
    }, "Enter a valid http or https URL, for example https://example.com"),
  description: z.string().max(2000).optional(),
});
type FormValues = z.infer<typeof schema>;

export function WebsiteForm({ initial, onDone }: { initial?: Website; onDone: (w: Website) => void }) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: initial?.name ?? "", url: initial?.url ?? "", description: initial?.description ?? "" },
  });
  const onSubmit = handleSubmit(async (v) => {
    setError(null);
    try {
      const w = initial ? await patch<Website>(`/websites/${initial.id}`, v) : await post<Website>("/websites", v);
      await qc.invalidateQueries({ queryKey: ["websites"] });
      await qc.invalidateQueries({ queryKey: ["website", w.id] });
      await qc.invalidateQueries({ queryKey: ["dashboard"] });
      onDone(w);
    } catch (e) {
      setError((e as Error).message);
    }
  });
  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {error && <Alert tone="error" live>{error}</Alert>}
      <TextField label="Name" required error={formState.errors.name?.message} {...register("name")} />
      <TextField label="URL" required type="url" inputMode="url" placeholder="https://example.com" hint="Only scan websites you own or are authorised to test. Private and internal addresses are blocked." error={formState.errors.url?.message} {...register("url")} />
      <TextArea label="Description" error={formState.errors.description?.message} {...register("description")} />
      <div className="flex justify-end gap-2">
        <Button type="submit" loading={formState.isSubmitting}>{initial ? "Save changes" : "Add website"}</Button>
      </div>
    </form>
  );
}

export default function Websites() {
  usePageTitle("Websites");
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState(params.get("add") === "1");
  const [showArchived, setShowArchived] = useState(false);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["websites", showArchived],
    queryFn: () => api<Website[]>(`/websites${qs({ include_archived: showArchived })}`),
  });
  const restore = useMutation({
    mutationFn: (id: string) => patch(`/websites/${id}`, { is_archived: false }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["websites"] }),
  });

  // "?add=1" (from the dashboard) opens the dialog once; remove it from the URL straight away so that it
  // cannot later replace the navigation to the newly created website.
  useEffect(() => {
    if (params.get("add") === "1") {
      const next = new URLSearchParams(params);
      next.delete("add");
      setParams(next, { replace: true });
    }
  }, [params, setParams]);

  return (
    <>
      <PageHeader
        title="Websites"
        description="The websites and projects you audit. Each website keeps its own scan history, analytics and monitoring settings."
        actions={<Button onClick={() => setOpen(true)} icon={<Plus className="h-4 w-4" aria-hidden="true" />}>Add website</Button>}
      />
      <div className="mb-4">
        <Checkbox label="Show archived websites" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
      </div>
      {isLoading && <Spinner label="Loading websites" />}
      {error && <Alert tone="error">{(error as Error).message}</Alert>}
      {data && data.length === 0 && (
        <EmptyState icon={<Globe className="h-10 w-10" />} title="No websites yet" action={<Button onClick={() => setOpen(true)}>Add a website</Button>}>
          Add a website to start auditing its accessibility.
        </EmptyState>
      )}
      {data && data.length > 0 && (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((w) => (
            <li key={w.id} className="flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-start gap-3">
                <ScoreRing score={w.latest_score} size={56} />
                <div className="min-w-0 flex-1">
                  <h2 className="truncate text-lg font-semibold text-navy-900">
                    <Link to={`/websites/${w.id}`} className="underline decoration-slate-300 hover:decoration-navy-800">{w.name}</Link>
                  </h2>
                  <p className="truncate text-sm text-slate-700">{w.url}</p>
                  {w.is_archived && <p className="text-xs font-medium text-amber-900">Archived</p>}
                </div>
              </div>
              {w.description && <p className="mt-3 line-clamp-2 text-sm text-slate-700">{w.description}</p>}
              <dl className="mt-4 grid grid-cols-3 gap-2 text-sm">
                <div><dt className="text-slate-700">Scans</dt><dd className="font-semibold">{w.scan_count}</dd></div>
                <div><dt className="text-slate-700">Open violations</dt><dd className="font-semibold">{w.open_violations}</dd></div>
                <div><dt className="text-slate-700">Last scan</dt><dd className="font-semibold">{w.latest_scan_status ? <StatusBadge status={w.latest_scan_status} /> : "—"}</dd></div>
              </dl>
              <p className="mt-2 text-xs text-slate-700">Last scanned {relativeTime(w.latest_scan_at)}{w.monitoring_enabled ? " · Monitoring on" : ""}</p>
              <div className="mt-4 flex gap-2">
                {w.is_archived ? (
                  <Button size="sm" variant="secondary" onClick={() => restore.mutate(w.id)} loading={restore.isPending && restore.variables === w.id}>Restore</Button>
                ) : (
                  <ButtonLink size="sm" to={`/scans/new?website=${w.id}`}><ScanSearch className="h-4 w-4" aria-hidden="true" />Scan<span className="sr-only"> {w.name}</span></ButtonLink>
                )}
                <ButtonLink size="sm" variant="secondary" to={`/websites/${w.id}`}>Details<span className="sr-only"> for {w.name}</span></ButtonLink>
              </div>
            </li>
          ))}
        </ul>
      )}
      <Dialog open={open} onOpenChange={setOpen} title="Add website" description="Enter the address of a website you are responsible for.">
        <WebsiteForm onDone={(w) => { setOpen(false); navigate(`/websites/${w.id}`); }} />
      </Dialog>
    </>
  );
}
