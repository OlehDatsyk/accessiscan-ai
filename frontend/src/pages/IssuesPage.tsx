import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { Website } from "../api/types";
import { IssuesTable } from "../components/IssuesTable";
import { usePageTitle } from "../components/Layout";
import { Alert, PageHeader, SelectField } from "../components/ui";

export default function IssuesPage() {
  usePageTitle("Issues");
  const [params] = useSearchParams();
  const [websiteId, setWebsiteId] = useState(params.get("website") ?? "");
  const sites = useQuery({ queryKey: ["websites", false], queryFn: () => api<Website[]>("/websites") });
  return (
    <>
      <PageHeader title="Issues" description="Issues from the latest completed scan of each active website. Filter, search and track remediation status." />
      <Alert tone="info" className="mb-4">
        Marking an issue as fixed records your decision; it only counts as resolved once a later scan no longer detects it.
      </Alert>
      <div className="mb-4 max-w-sm">
        <SelectField label="Website" value={websiteId} onChange={(e) => setWebsiteId(e.target.value)}>
          <option value="">All websites</option>
          {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </SelectField>
      </div>
      <IssuesTable key={websiteId} websiteId={websiteId || undefined} initial={{ impact: params.getAll("impact") }} />
    </>
  );
}
