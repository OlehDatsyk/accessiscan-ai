/**
 * Charts (Recharts) with an accessible data-table alternative for every chart: the table is always
 * available to screen readers and can be shown visually with a toggle.
 */
import { useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export const SEVERITY_COLORS: Record<string, string> = {
  critical: "#b91c1c",
  serious: "#c2410c",
  moderate: "#a16207",
  minor: "#475569",
};

export const SERIES = ["#1b3563", "#0d8278", "#b45309", "#7c3aed", "#be123c", "#0369a1"];

interface Column {
  key: string;
  label: string;
}

export function ChartFigure({
  title,
  description,
  rows,
  columns,
  children,
  height = 260,
}: {
  title: string;
  description?: string;
  rows: Record<string, unknown>[];
  columns: Column[];
  children: ReactNode;
  height?: number;
}) {
  const [showTable, setShowTable] = useState(false);
  const id = title.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  return (
    <figure className="m-0 rounded-xl border border-slate-200 bg-white p-4 shadow-sm" aria-labelledby={`${id}-title`}>
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <figcaption id={`${id}-title`} className="font-semibold text-navy-900">{title}</figcaption>
          {description && <p className="text-xs text-slate-700">{description}</p>}
        </div>
        {rows.length > 0 && (
          <button
            type="button"
            className="shrink-0 rounded px-2 py-1 text-xs font-medium text-navy-800 underline hover:bg-navy-50"
            aria-pressed={showTable}
            onClick={() => setShowTable((v) => !v)}
          >
            {showTable ? "Show chart" : "Show data table"}
          </button>
        )}
      </div>
      {rows.length === 0 ? (
        <p className="py-10 text-center text-sm text-slate-700">No data yet. Complete a scan to see this chart.</p>
      ) : (
        <>
          {/* The chart is a visual duplicate of the data table below, so it is hidden from assistive technology
              and made inert (Recharts adds focusable elements to its SVG). */}
          <div aria-hidden="true" inert className={showTable ? "hidden" : undefined} style={{ height }}>
            <ResponsiveContainer width="100%" height="100%">{children as React.ReactElement}</ResponsiveContainer>
          </div>
          <div className={showTable ? "max-h-72 overflow-auto" : "sr-only"}>
            <table className="w-full text-left text-sm">
              <caption className="sr-only">{title} (data table)</caption>
              <thead>
                <tr>
                  {columns.map((c) => (
                    <th key={c.key} scope="col" className="border-b border-slate-200 px-2 py-1 font-semibold">{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-b border-slate-100">
                    {columns.map((c) => (
                      <td key={c.key} className="px-2 py-1">{String(r[c.key] ?? "—")}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </figure>
  );
}

export function SeverityBarChart({ data, title }: { data: Record<string, number>; title: string }) {
  const rows = ["critical", "serious", "moderate", "minor"].map((k) => ({ severity: k[0].toUpperCase() + k.slice(1), key: k, count: data[k] ?? 0 }));
  const total = rows.reduce((a, r) => a + r.count, 0);
  return (
    <ChartFigure title={title} description="Affected elements on the latest completed scans" rows={total ? rows : []} columns={[{ key: "severity", label: "Severity" }, { key: "count", label: "Elements" }]}>
      <BarChart data={rows} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="severity" tick={{ fill: "#334155", fontSize: 12 }} />
        <YAxis allowDecimals={false} tick={{ fill: "#334155", fontSize: 12 }} />
        <Tooltip />
        <Bar dataKey="count" name="Elements" isAnimationActive={false}>
          {rows.map((r) => (
            <Cell key={r.key} fill={SEVERITY_COLORS[r.key]} />
          ))}
        </Bar>
      </BarChart>
    </ChartFigure>
  );
}

export function SimpleBarChart({ title, description, rows, x, y, yLabel, xLabel, color = SERIES[0], layout = "horizontal" }: { title: string; description?: string; rows: Record<string, string | number>[]; x: string; y: string; xLabel: string; yLabel: string; color?: string; layout?: "horizontal" | "vertical" }) {
  return (
    <ChartFigure title={title} description={description} rows={rows} columns={[{ key: x, label: xLabel }, { key: y, label: yLabel }]} height={layout === "vertical" ? Math.max(200, rows.length * 32) : 260}>
      {layout === "vertical" ? (
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" allowDecimals={false} tick={{ fill: "#334155", fontSize: 12 }} />
          <YAxis type="category" dataKey={x} width={150} tick={{ fill: "#334155", fontSize: 12 }} />
          <Tooltip />
          <Bar dataKey={y} name={yLabel} fill={color} isAnimationActive={false} />
        </BarChart>
      ) : (
        <BarChart data={rows} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey={x} tick={{ fill: "#334155", fontSize: 12 }} />
          <YAxis allowDecimals={false} tick={{ fill: "#334155", fontSize: 12 }} />
          <Tooltip />
          <Bar dataKey={y} name={yLabel} fill={color} isAnimationActive={false} />
        </BarChart>
      )}
    </ChartFigure>
  );
}

export function TrendChart({ title, description, rows, lines, x = "date", xLabel = "Date", domain }: { title: string; description?: string; rows: Record<string, string | number | null>[]; lines: { key: string; label: string; color: string }[]; x?: string; xLabel?: string; domain?: [number, number] }) {
  return (
    <ChartFigure title={title} description={description} rows={rows} columns={[{ key: x, label: xLabel }, ...lines.map((l) => ({ key: l.key, label: l.label }))]}>
      <LineChart data={rows} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey={x} tick={{ fill: "#334155", fontSize: 12 }} />
        <YAxis domain={domain} allowDecimals={false} tick={{ fill: "#334155", fontSize: 12 }} />
        <Tooltip />
        <Legend />
        {lines.map((l, i) => (
          <Line key={l.key} type="monotone" dataKey={l.key} name={l.label} stroke={l.color} strokeWidth={2} strokeDasharray={i % 2 ? "5 3" : undefined} dot={{ r: 3 }} isAnimationActive={false} connectNulls />
        ))}
      </LineChart>
    </ChartFigure>
  );
}

export function GroupedBarChart({ title, description, rows, bars, x = "date", xLabel = "Date" }: { title: string; description?: string; rows: Record<string, string | number>[]; bars: { key: string; label: string; color: string }[]; x?: string; xLabel?: string }) {
  return (
    <ChartFigure title={title} description={description} rows={rows} columns={[{ key: x, label: xLabel }, ...bars.map((b) => ({ key: b.key, label: b.label }))]}>
      <BarChart data={rows} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={x} tick={{ fill: "#334155", fontSize: 12 }} />
        <YAxis allowDecimals={false} tick={{ fill: "#334155", fontSize: 12 }} />
        <Tooltip />
        <Legend />
        {bars.map((b) => (
          <Bar key={b.key} dataKey={b.key} name={b.label} fill={b.color} isAnimationActive={false} />
        ))}
      </BarChart>
    </ChartFigure>
  );
}
