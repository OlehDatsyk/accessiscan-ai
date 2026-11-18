import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ScanSearch } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, post } from "../api/client";
import type { Scan, Website } from "../api/types";
import { usePageTitle } from "../components/Layout";
import { Alert, Button, Card, Checkbox, PageHeader, SelectField, Spinner, TextArea, TextField } from "../components/ui";

type Mode = "single" | "list" | "crawl";

export default function NewScan() {
  usePageTitle("New scan");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const sites = useQuery({ queryKey: ["websites", false], queryFn: () => api<Website[]>("/websites") });
  const [websiteId, setWebsiteId] = useState(params.get("website") ?? "");
  const [mode, setMode] = useState<Mode>("single");
  const [urls, setUrls] = useState("");
  const [maxPages, setMaxPages] = useState(5);
  const [maxDepth, setMaxDepth] = useState(1);
  const [includeAAA, setIncludeAAA] = useState(false);
  const [robots, setRobots] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const site = sites.data?.find((s) => s.id === websiteId) ?? (sites.data?.length === 1 ? sites.data[0] : undefined);
  const effectiveId = site?.id ?? "";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setFieldError(null);
    if (!effectiveId) {
      setFieldError("Choose a website to scan");
      return;
    }
    const list = urls.split(/\s+/).map((u) => u.trim()).filter(Boolean);
    if (mode === "list" && list.length === 0) {
      setError("Enter at least one URL to scan, one per line.");
      return;
    }
    setSubmitting(true);
    try {
      const scan = await post<Scan>("/scans", {
        website_id: effectiveId,
        mode,
        urls: mode === "list" ? list : [],
        max_pages: mode === "crawl" ? maxPages : mode === "list" ? Math.max(list.length, 1) : 1,
        max_depth: maxDepth,
        include_aaa: includeAAA,
        respect_robots: robots,
      });
      qc.invalidateQueries({ queryKey: ["scans"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      navigate(`/scans/${scan.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  if (sites.isLoading) return <Spinner />;
  if (sites.data && sites.data.length === 0) {
    return (
      <>
        <PageHeader title="New scan" />
        <Alert tone="info" title="Add a website first">
          Scans belong to a website. <Link to="/websites?add=1" className="font-medium underline">Add a website</Link> and then start a scan.
        </Alert>
      </>
    );
  }

  return (
    <>
      <PageHeader title="New scan" description="AccessiScan opens each page in a real Chromium browser, runs axe-core accessibility rules and stores every result." />
      <form onSubmit={submit} noValidate className="grid gap-6 lg:grid-cols-3">
        <Card className="flex flex-col gap-5 lg:col-span-2">
          {error && <Alert tone="error" live>{error}</Alert>}
          <SelectField label="Website" required value={effectiveId} onChange={(e) => setWebsiteId(e.target.value)} error={fieldError ?? undefined}>
            <option value="">Choose a website…</option>
            {sites.data?.map((s) => (
              <option key={s.id} value={s.id}>{s.name} — {s.url}</option>
            ))}
          </SelectField>

          <fieldset>
            <legend className="text-sm font-medium text-slate-900">Scan type</legend>
            <div className="mt-2 grid gap-2 sm:grid-cols-3">
              {([
                ["single", "Single page", "The website's URL only"],
                ["list", "List of URLs", "Specific pages you choose"],
                ["crawl", "Limited crawl", "Follow same-site links"],
              ] as [Mode, string, string][]).map(([value, label, desc]) => (
                <label key={value} className={`flex cursor-pointer flex-col rounded-lg border p-3 ${mode === value ? "border-navy-700 bg-navy-50 ring-1 ring-navy-700" : "border-slate-300"}`}>
                  <span className="flex items-center gap-2 font-medium">
                    <input type="radio" name="mode" value={value} checked={mode === value} onChange={() => setMode(value)} className="accent-navy-800" />
                    {label}
                  </span>
                  <span className="mt-1 text-xs text-slate-700">{desc}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {mode === "list" && (
            <TextArea
              label="Page URLs"
              required
              hint={`One URL per line, all on ${site ? new URL(site.url).host : "the website's domain"}. Up to 50 URLs.`}
              value={urls}
              onChange={(e) => setUrls(e.target.value)}
              rows={6}
              placeholder={site ? `${site.url}\n${new URL("about", site.url).href}` : "https://example.com/"}
            />
          )}

          {mode === "crawl" && (
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField label="Maximum pages" type="number" min={1} max={50} value={maxPages} onChange={(e) => setMaxPages(Math.min(50, Math.max(1, Number(e.target.value) || 1)))} hint="The server may enforce a lower limit." />
              <TextField label="Maximum link depth" type="number" min={0} max={5} value={maxDepth} onChange={(e) => setMaxDepth(Math.min(5, Math.max(0, Number(e.target.value) || 0)))} hint="0 = start page only, 1 = pages linked from it." />
              <div className="sm:col-span-2">
                <Checkbox label="Respect robots.txt" description="Skip pages that the site's robots.txt disallows for crawlers." checked={robots} onChange={(e) => setRobots(e.target.checked)} />
              </div>
            </div>
          )}

          <Checkbox label="Include WCAG AAA rules" description="Adds axe-core's AAA rules (for example enhanced contrast). AAA conformance is not required by most policies." checked={includeAAA} onChange={(e) => setIncludeAAA(e.target.checked)} />

          <div>
            <Button type="submit" size="lg" loading={submitting} icon={<ScanSearch className="h-4 w-4" aria-hidden="true" />}>Start scan</Button>
          </div>
        </Card>

        <Card as="div" className="h-fit text-sm text-slate-800">
          <h2 className="mb-2 font-semibold text-navy-900">What gets tested</h2>
          <ul className="list-disc space-y-1 pl-5">
            <li>WCAG 2.0, 2.1 and 2.2 Level A and AA rules from axe-core, plus best practices.</li>
            <li>Images, colour contrast, forms, ARIA, landmarks, headings, language, keyboard-related names and roles.</li>
            <li>Pages are loaded as an anonymous visitor: content behind logins is not tested.</li>
          </ul>
          <h2 className="mb-2 mt-4 font-semibold text-navy-900">Safety limits</h2>
          <ul className="list-disc space-y-1 pl-5">
            <li>Only public http/https addresses; private networks are blocked.</li>
            <li>Page, depth, time and download-size limits are enforced on the server.</li>
            <li>Only scan websites you own or are authorised to test.</li>
          </ul>
        </Card>
      </form>
    </>
  );
}
