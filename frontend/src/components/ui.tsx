/**
 * Accessible UI primitives. Native HTML elements are used wherever possible (button, select, input,
 * table); Radix Dialog provides focus-trapped, labelled modal dialogs.
 */
import * as RadixDialog from "@radix-ui/react-dialog";
import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Info, Loader2, X, XCircle } from "lucide-react";
import {
  forwardRef,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { Link, type LinkProps } from "react-router-dom";
import type { Impact } from "../api/types";
import { IMPACT_LABEL, STATUS_LABEL } from "../lib/format";

type Variant = "primary" | "secondary" | "danger" | "ghost";
const variants: Record<Variant, string> = {
  primary: "bg-navy-800 text-white hover:bg-navy-700 disabled:bg-slate-400",
  secondary: "bg-white text-navy-900 border border-slate-300 hover:bg-slate-100 disabled:text-slate-500",
  danger: "bg-red-700 text-white hover:bg-red-800 disabled:bg-slate-400",
  ghost: "text-navy-800 hover:bg-navy-100 disabled:text-slate-500",
};
const sizes = { sm: "px-2.5 py-1.5 text-sm", md: "px-4 py-2 text-sm", lg: "px-5 py-2.5 text-base" };

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: keyof typeof sizes;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, icon, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors disabled:cursor-not-allowed",
        "min-h-[2.25rem]",
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : icon}
      {children}
    </button>
  );
});

export function ButtonLink({ variant = "primary", size = "md", className, ...rest }: LinkProps & { variant?: Variant; size?: keyof typeof sizes }) {
  return (
    <Link
      className={clsx(
        "inline-flex min-h-[2.25rem] items-center justify-center gap-2 rounded-md font-medium no-underline transition-colors",
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    />
  );
}

export function Card({ className, children, as: As = "section", ...rest }: { className?: string; children: ReactNode; as?: "section" | "div" | "article"; "aria-labelledby"?: string }) {
  return (
    <As className={clsx("rounded-xl border border-slate-200 bg-white p-5 shadow-sm", className)} {...rest}>
      {children}
    </As>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-navy-900">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-slate-700">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

const impactStyle: Record<Impact, string> = {
  critical: "bg-red-100 text-red-900 border-red-300",
  serious: "bg-orange-100 text-orange-900 border-orange-300",
  moderate: "bg-amber-100 text-amber-900 border-amber-300",
  minor: "bg-slate-100 text-slate-800 border-slate-300",
};

export function ImpactBadge({ impact }: { impact: Impact }) {
  return (
    <span className={clsx("inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold", impactStyle[impact])}>
      {IMPACT_LABEL[impact] ?? impact}
    </span>
  );
}

const statusStyle: Record<string, string> = {
  open: "bg-sky-100 text-sky-900",
  in_progress: "bg-indigo-100 text-indigo-900",
  marked_fixed: "bg-emerald-100 text-emerald-900",
  ignored: "bg-slate-200 text-slate-800",
  queued: "bg-slate-200 text-slate-800",
  running: "bg-sky-100 text-sky-900",
  completed: "bg-emerald-100 text-emerald-900",
  failed: "bg-red-100 text-red-900",
  cancelled: "bg-slate-200 text-slate-800",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", statusStyle[status] ?? "bg-slate-100 text-slate-800")}>
      {status === "running" && <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />}
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function Tag({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "teal" | "navy" }) {
  const tones = { slate: "bg-slate-100 text-slate-800", teal: "bg-accent-100 text-accent-700", navy: "bg-navy-100 text-navy-800" };
  return <span className={clsx("inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium", tones[tone])}>{children}</span>;
}

type AlertTone = "info" | "success" | "warning" | "error";
const alertStyle: Record<AlertTone, [string, typeof Info]> = {
  info: ["border-sky-300 bg-sky-50 text-sky-950", Info],
  success: ["border-emerald-300 bg-emerald-50 text-emerald-950", CheckCircle2],
  warning: ["border-amber-300 bg-amber-50 text-amber-950", AlertTriangle],
  error: ["border-red-300 bg-red-50 text-red-950", XCircle],
};

export function Alert({ tone = "info", title, children, className, live }: { tone?: AlertTone; title?: string; children?: ReactNode; className?: string; live?: boolean }) {
  const [style, Icon] = alertStyle[tone];
  return (
    <div role={live ? (tone === "error" ? "alert" : "status") : undefined} className={clsx("flex gap-3 rounded-lg border p-3 text-sm", style, className)}>
      <Icon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
      <div>
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={clsx(title && "mt-0.5")}>{children}</div>}
      </div>
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-8 text-slate-700">
      <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
      <span>{label}…</span>
    </div>
  );
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
      {icon && <div className="mb-3 text-accent-700" aria-hidden="true">{icon}</div>}
      <h2 className="text-lg font-semibold text-navy-900">{title}</h2>
      {children && <div className="mt-1 max-w-md text-slate-700">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// ----------------------------------------------------------------------------- form fields
interface FieldShell {
  label: string;
  error?: string;
  hint?: ReactNode;
  required?: boolean;
}

function FieldWrap({ id, label, error, hint, required, children }: FieldShell & { id: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-slate-900">
        {label}
        {required && <span className="text-red-800"> (required)</span>}
      </label>
      {hint && <p id={`${id}-hint`} className="text-xs text-slate-700">{hint}</p>}
      {children}
      {error && (
        <p id={`${id}-error`} className="flex items-center gap-1 text-sm text-red-800">
          <XCircle className="h-4 w-4" aria-hidden="true" /> {error}
        </p>
      )}
    </div>
  );
}

const inputClass =
  "w-full rounded-md border border-slate-400 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-600 focus:border-accent-600 aria-[invalid=true]:border-red-700";

function describedBy(id: string, hint?: ReactNode, error?: string) {
  return [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
}

export const TextField = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & FieldShell>(function TextField(
  { label, error, hint, required, id: idProp, className, ...rest },
  ref,
) {
  const auto = useId();
  const id = idProp ?? auto;
  return (
    <FieldWrap id={id} label={label} error={error} hint={hint} required={required}>
      <input
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-required={required || undefined}
        aria-describedby={describedBy(id, hint, error)}
        className={clsx(inputClass, className)}
        {...rest}
      />
    </FieldWrap>
  );
});

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement> & FieldShell>(function TextArea(
  { label, error, hint, required, id: idProp, className, ...rest },
  ref,
) {
  const auto = useId();
  const id = idProp ?? auto;
  return (
    <FieldWrap id={id} label={label} error={error} hint={hint} required={required}>
      <textarea
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-required={required || undefined}
        aria-describedby={describedBy(id, hint, error)}
        className={clsx(inputClass, "min-h-24", className)}
        {...rest}
      />
    </FieldWrap>
  );
});

export const SelectField = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement> & FieldShell>(function SelectField(
  { label, error, hint, required, id: idProp, className, children, ...rest },
  ref,
) {
  const auto = useId();
  const id = idProp ?? auto;
  return (
    <FieldWrap id={id} label={label} error={error} hint={hint} required={required}>
      <select
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, hint, error)}
        className={clsx(inputClass, "pr-8", className)}
        {...rest}
      >
        {children}
      </select>
    </FieldWrap>
  );
});

export function Checkbox({ label, description, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: string; description?: string }) {
  const id = useId();
  return (
    <div className="flex items-start gap-2">
      <input id={id} type="checkbox" className="mt-1 h-4 w-4 rounded border-slate-500 accent-navy-800" aria-describedby={description ? `${id}-d` : undefined} {...rest} />
      <div>
        <label htmlFor={id} className="text-sm font-medium text-slate-900">{label}</label>
        {description && <p id={`${id}-d`} className="text-xs text-slate-700">{description}</p>}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------- dialog
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  wide,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  wide?: boolean;
}) {
  // Remember what had focus when the dialog opened and return focus there on close (WCAG 2.4.3).
  // Radix only restores focus automatically when <Dialog.Trigger> is used.
  const returnFocus = useRef<HTMLElement | null>(null);
  if (open && returnFocus.current === null && typeof document !== "undefined") {
    returnFocus.current = document.activeElement as HTMLElement | null;
  }
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-navy-950/60" />
        <RadixDialog.Content
          className={clsx(
            "fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl bg-white p-6 shadow-xl",
            wide ? "max-w-2xl" : "max-w-lg",
          )}
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            const el = returnFocus.current;
            returnFocus.current = null;
            if (el && document.contains(el)) el.focus();
          }}
        >
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <RadixDialog.Title className="text-lg font-semibold text-navy-900">{title}</RadixDialog.Title>
              {description ? (
                <RadixDialog.Description className="mt-1 text-sm text-slate-700">{description}</RadixDialog.Description>
              ) : (
                <RadixDialog.Description className="sr-only">{title}</RadixDialog.Description>
              )}
            </div>
            <RadixDialog.Close asChild>
              <button type="button" className="rounded p-1 text-slate-700 hover:bg-slate-100" aria-label="Close dialog">
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </RadixDialog.Close>
          </div>
          {children}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  onConfirm,
  loading,
  danger = true,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
  loading?: boolean;
  danger?: boolean;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={title} description={description}>
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
        <Button variant={danger ? "danger" : "primary"} loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
      </div>
    </Dialog>
  );
}

// ----------------------------------------------------------------------------- tabs (WAI-ARIA tabs pattern)
export function Tabs<T extends string>({ label, tabs, value, onChange, idPrefix }: { label: string; tabs: { id: T; label: string; count?: number }[]; value: T; onChange: (v: T) => void; idPrefix: string }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: KeyboardEvent, i: number) => {
    let next = -1;
    if (e.key === "ArrowRight") next = (i + 1) % tabs.length;
    if (e.key === "ArrowLeft") next = (i - 1 + tabs.length) % tabs.length;
    if (e.key === "Home") next = 0;
    if (e.key === "End") next = tabs.length - 1;
    if (next >= 0) {
      e.preventDefault();
      onChange(tabs[next].id);
      refs.current[next]?.focus();
    }
  };
  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-1 border-b border-slate-200">
      {tabs.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          role="tab"
          type="button"
          id={`${idPrefix}-tab-${t.id}`}
          aria-selected={value === t.id}
          aria-controls={`${idPrefix}-panel-${t.id}`}
          tabIndex={value === t.id ? 0 : -1}
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => onKey(e, i)}
          className={clsx(
            "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
            value === t.id ? "border-accent-600 text-navy-900" : "border-transparent text-slate-700 hover:text-navy-900",
          )}
        >
          {t.label}
          {t.count !== undefined && <span className="ml-1.5 rounded-full bg-slate-100 px-1.5 text-xs text-slate-800">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ idPrefix, id, children }: { idPrefix: string; id: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={`${idPrefix}-panel-${id}`} aria-labelledby={`${idPrefix}-tab-${id}`} tabIndex={0} className="pt-4 focus-visible:outline-offset-4">
      {children}
    </div>
  );
}

// ----------------------------------------------------------------------------- misc
export function StatCard({ label, value, hint, icon, tone = "navy" }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode; tone?: "navy" | "red" | "teal" | "amber" }) {
  const tones = { navy: "text-navy-800 bg-navy-100", red: "text-red-800 bg-red-100", teal: "text-accent-700 bg-accent-100", amber: "text-amber-900 bg-amber-100" };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <dt className="flex items-start justify-between gap-2 text-sm font-medium text-slate-700">
        <span>{label}</span>
        {icon && <span className={clsx("rounded-md p-1.5", tones[tone])} aria-hidden="true">{icon}</span>}
      </dt>
      <dd className="mt-2 text-2xl font-semibold text-navy-900">{value}</dd>
      {hint && <dd className="mt-1 text-xs text-slate-700">{hint}</dd>}
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <nav aria-label="Pagination" className="mt-4 flex items-center justify-between gap-2 text-sm">
      <p className="text-slate-700">
        Page {page} of {pages} ({total} items)
      </p>
      <div className="flex gap-2">
        <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </nav>
  );
}

export function CodeBlock({ code, label }: { code: string; label: string }) {
  return (
    <figure className="m-0">
      <figcaption className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-700">{label}</figcaption>
      {/* Rendered as text, never as HTML: scanned markup is untrusted. Scrollable, so it must be keyboard-focusable (WCAG 2.1.1). */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
      <pre className="code-block max-h-64 overflow-auto rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-900" tabIndex={0}>
        <code>{code}</code>
      </pre>
    </figure>
  );
}

export function VisuallyHidden({ children }: { children: ReactNode }) {
  return <span className="sr-only">{children}</span>;
}

export function ScoreRing({ score, size = 96 }: { score: number | null | undefined; size?: number }) {
  const s = score ?? 0;
  const r = 40;
  const c = 2 * Math.PI * r;
  const color = score === null || score === undefined ? "#64748b" : s >= 90 ? "#047857" : s >= 70 ? "#b45309" : "#b91c1c";
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" role="img" aria-label={score === null || score === undefined ? "Not scored" : `Score ${s} out of 100`}>
      <circle cx="50" cy="50" r={r} fill="none" stroke="#e2e8f0" strokeWidth="10" />
      <circle cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="10" strokeLinecap="round" strokeDasharray={`${(s / 100) * c} ${c}`} transform="rotate(-90 50 50)" />
      <text x="50" y="56" textAnchor="middle" fontSize="22" fontWeight="700" fill="#0b1a33">
        {score === null || score === undefined ? "–" : Math.round(s)}
      </text>
    </svg>
  );
}
