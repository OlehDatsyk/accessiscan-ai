import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

interface Meta {
  version: string;
  ephemeral_demo: boolean;
  registration_enabled: boolean;
  docs_enabled: boolean;
}

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

/** Permanent notice for demo deployments whose database is wiped on restart. Render inside a landmark. */
export function DemoBanner() {
  const { data } = useQuery({
    queryKey: ["meta"],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/api/v1/meta`);
      if (!r.ok) throw new Error("meta unavailable");
      return (await r.json()) as Meta;
    },
    staleTime: Infinity,
    retry: 1,
  });
  if (!data?.ephemeral_demo) return null;
  return (
    <p className="flex w-full items-start gap-2 bg-amber-100 px-4 py-2 text-sm text-amber-950">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>
        <strong>Demo deployment:</strong> data is temporary and is deleted whenever the server restarts, redeploys or sleeps
        after inactivity. Do not store anything you need to keep.
      </span>
    </p>
  );
}
