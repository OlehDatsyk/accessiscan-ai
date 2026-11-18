import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Send } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, post, qs } from "../api/client";
import type { AIStatus, Issue, Paged, Scan } from "../api/types";
import { usePageTitle } from "../components/Layout";
import { Alert, Button, Card, CodeBlock, PageHeader, SelectField, Spinner, TextArea } from "../components/ui";
import { formatDate } from "../lib/format";

interface Answer {
  answer: string;
  referenced_issue_ids: string[];
  code_example: string | null;
  code_language: string;
  verification_steps: string[];
  wcag_references: string[];
  provider: string;
  model: string;
  label: string;
  context_issue_ids: string[];
}

const SUGGESTIONS = [
  "Why is this an accessibility problem?",
  "Who might be affected?",
  "How can I fix this? Show an example of corrected HTML.",
  "What should I fix first?",
  "Which issues may have the greatest impact on users?",
  "How can I test this manually?",
];

export default function Assistant() {
  usePageTitle("AI assistant");
  const [params] = useSearchParams();
  const [scanId, setScanId] = useState(params.get("scan") ?? "");
  const [issueId, setIssueId] = useState(params.get("issue") ?? "");
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<{ q: string; a: Answer }[]>([]);
  const status = useQuery({ queryKey: ["ai-status"], queryFn: () => api<AIStatus>("/ai/status") });
  const scans = useQuery({ queryKey: ["scans", { completed: true, all: true }], queryFn: () => api<Paged<Scan>>(`/scans${qs({ status: "completed", page_size: 50 })}`) });
  const issues = useQuery({
    queryKey: ["issues", { scan: scanId, assistant: true }],
    queryFn: () => api<Paged<Issue>>(`/issues${qs({ scan_id: scanId, page_size: 200 })}`),
    enabled: !!scanId,
  });
  const ask = useMutation({
    mutationFn: (q: string) => post<Answer>("/ai/ask", { scan_id: scanId, question: q, issue_ids: issueId ? [issueId] : [] }),
    onSuccess: (a, q) => {
      setHistory((h) => [{ q, a }, ...h]);
      setQuestion("");
    },
    onError: (e) => setError((e as Error).message),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!scanId) return setError("Choose a scan first.");
    if (question.trim().length < 3) return setError("Enter a question.");
    ask.mutate(question.trim());
  };
  const issueById = new Map((issues.data?.items ?? []).map((i) => [i.id, i]));

  return (
    <>
      <PageHeader title="AI accessibility assistant" description="Ask questions about the issues detected in one of your scans. Answers are based only on the stored scan results." />
      {status.isLoading ? <Spinner /> : !status.data?.enabled ? (
        <Alert tone="warning" title="AI is not configured" className="mb-6">
          {status.data?.message} You can still use the built-in guidance on each issue's page and the rule documentation links.
        </Alert>
      ) : (
        <p className="mb-4 text-sm text-slate-700">Using {status.data.provider} / {status.data.model} · {status.data.used_today} of {status.data.daily_limit} requests used in the last 24 hours.</p>
      )}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="h-fit">
          <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
            <SelectField label="Scan" required value={scanId} onChange={(e) => { setScanId(e.target.value); setIssueId(""); }}>
              <option value="">Choose a completed scan…</option>
              {scans.data?.items.map((s) => <option key={s.id} value={s.id}>{s.website_name} – {formatDate(s.created_at)}</option>)}
            </SelectField>
            <SelectField label="Focus on one issue (optional)" value={issueId} onChange={(e) => setIssueId(e.target.value)} disabled={!scanId} hint="Without a selection the assistant receives the most severe issue of each failing rule.">
              <option value="">Most severe issues of this scan</option>
              {issues.data?.items.map((i) => <option key={i.id} value={i.id}>[{i.impact}] {i.help.slice(0, 70)} – {i.selector.slice(0, 40)}</option>)}
            </SelectField>
            <TextArea label="Your question" required value={question} onChange={(e) => setQuestion(e.target.value)} rows={4} maxLength={2000} />
            <div>
              <p className="mb-1 text-xs font-medium text-slate-700">Suggested questions</p>
              <div className="flex flex-wrap gap-1">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="rounded-full border border-slate-300 px-2 py-1 text-xs text-navy-900 hover:bg-slate-100" onClick={() => setQuestion(s)}>{s}</button>
                ))}
              </div>
            </div>
            {error && <Alert tone="error" live>{error}</Alert>}
            <Button type="submit" loading={ask.isPending} disabled={!status.data?.enabled} icon={<Send className="h-4 w-4" aria-hidden="true" />}>Ask</Button>
          </form>
        </Card>
        <section className="lg:col-span-2" aria-labelledby="answers-h" aria-live="polite">
          <h2 id="answers-h" className="mb-3 font-semibold text-navy-900">Answers</h2>
          {ask.isPending && <Spinner label="Waiting for the AI provider" />}
          {history.length === 0 && !ask.isPending && (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-slate-700">
              <Bot className="mx-auto mb-2 h-8 w-8 text-accent-700" aria-hidden="true" />
              Answers appear here. Generated code is a suggestion and is never applied to your website.
            </div>
          )}
          <ol className="space-y-4">
            {history.map(({ q, a }, idx) => (
              <li key={idx}>
                <Card as="article">
                  <h3 className="font-semibold text-navy-900">{q}</h3>
                  <p className="mt-1 inline-block rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-950">{a.label}</p>
                  <p className="mt-3 whitespace-pre-wrap text-sm">{a.answer}</p>
                  {a.code_example && <div className="mt-3"><CodeBlock label={`Suggested ${a.code_language} (example – adapt and test)`} code={a.code_example} /></div>}
                  {a.verification_steps.length > 0 && (
                    <div className="mt-3 text-sm"><p className="font-semibold">How to verify</p><ol className="list-decimal pl-5">{a.verification_steps.map((v) => <li key={v}>{v}</li>)}</ol></div>
                  )}
                  {a.wcag_references.length > 0 && <p className="mt-2 text-sm"><strong>WCAG:</strong> {a.wcag_references.join(", ")}</p>}
                  {a.referenced_issue_ids.length > 0 && (
                    <p className="mt-2 text-sm">
                      <strong>Issues discussed:</strong>{" "}
                      {a.referenced_issue_ids.map((id, n) => (
                        <span key={id}>{n > 0 && ", "}<Link to={`/issues/${id}`} className="text-navy-800 underline">{issueById.get(id)?.rule_id ?? "issue"}</Link></span>
                      ))}
                    </p>
                  )}
                  <p className="mt-2 text-xs text-slate-700">{a.provider} / {a.model} · context: {a.context_issue_ids.length} detected issue(s)</p>
                </Card>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </>
  );
}
