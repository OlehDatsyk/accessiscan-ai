import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Bell,
  Bot,
  ClipboardList,
  FileText,
  Gauge,
  Globe,
  LogOut,
  Menu,
  Palette,
  Radar,
  ScanSearch,
  Settings,
  X,
} from "lucide-react";
import { Suspense, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, post } from "../api/client";
import type { Notification } from "../api/types";
import { useAuth } from "../lib/auth";
import { relativeTime } from "../lib/format";

const NAV = [
  { to: "/", label: "Dashboard", icon: Gauge, end: true },
  { to: "/websites", label: "Websites", icon: Globe },
  { to: "/scans/new", label: "New scan", icon: ScanSearch },
  { to: "/scans", label: "Scan results", icon: Radar, end: true },
  { to: "/issues", label: "Issues", icon: ClipboardList },
  { to: "/assistant", label: "AI assistant", icon: Bot },
  { to: "/contrast", label: "Contrast checker", icon: Palette },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/monitoring", label: "Monitoring", icon: Bell },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = `${title} · AccessiScan AI`;
  }, [title]);
}

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2 rounded text-white no-underline">
      <svg width="32" height="32" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="7" fill="#12264a" />
        <circle cx="14" cy="14" r="7" fill="none" stroke="#2dd4bf" strokeWidth="3" />
        <path d="M19 19l6 6" stroke="#2dd4bf" strokeWidth="3" strokeLinecap="round" />
        <path d="M11 14l2 2 4-4" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="text-lg font-semibold tracking-tight">
        AccessiScan <span className="text-accent-300">AI</span>
      </span>
    </Link>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="on-dark flex flex-1 flex-col gap-1 px-3 py-4">
      <ul className="flex flex-col gap-1">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={end}
              onClick={onNavigate}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium no-underline",
                  isActive ? "bg-navy-700 text-white" : "text-slate-200 hover:bg-navy-800 hover:text-white",
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
      <p className="mt-auto px-3 pt-6 text-xs leading-relaxed text-slate-300">
        Automated results are not legal certification. Always complete manual accessibility testing.
      </p>
    </nav>
  );
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const panelRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const { data = [] } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<Notification[]>("/notifications"),
    refetchInterval: 30_000,
  });
  const unread = data.filter((n) => !n.is_read).length;
  const readAll = useMutation({
    mutationFn: () => post("/notifications/read-all"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const readOne = useMutation({
    mutationFn: (id: string) => post(`/notifications/${id}/read`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    const onClick = (e: MouseEvent) => {
      if (!panelRef.current?.contains(e.target as Node) && !buttonRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-controls="notifications-panel"
        onClick={() => setOpen((o) => !o)}
        className="relative rounded-md p-2 text-navy-900 hover:bg-slate-100"
      >
        <Bell className="h-5 w-5" aria-hidden="true" />
        <span className="sr-only">Notifications{unread ? ` (${unread} unread)` : ""}</span>
        {unread > 0 && (
          <span aria-hidden="true" className="absolute -right-0.5 -top-0.5 rounded-full bg-red-700 px-1.5 text-[11px] font-bold text-white">
            {unread}
          </span>
        )}
      </button>
      {open && (
        <div ref={panelRef} id="notifications-panel" role="region" aria-label="Notifications" className="absolute right-0 z-30 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
          <div className="flex items-center justify-between px-2 py-1">
            <h2 className="text-sm font-semibold text-navy-900">Notifications</h2>
            {unread > 0 && (
              <button type="button" className="text-xs font-medium text-navy-800 underline" onClick={() => readAll.mutate()}>
                Mark all as read
              </button>
            )}
          </div>
          {data.length === 0 ? (
            <p className="px-2 py-4 text-sm text-slate-700">No notifications yet.</p>
          ) : (
            <ul className="max-h-96 overflow-y-auto">
              {data.slice(0, 20).map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    className={clsx("w-full rounded-md px-2 py-2 text-left hover:bg-slate-50", !n.is_read && "bg-navy-50")}
                    onClick={() => {
                      readOne.mutate(n.id);
                      setOpen(false);
                      if (n.link) navigate(n.link);
                    }}
                  >
                    <span className="block text-sm font-medium text-navy-900">
                      {!n.is_read && <span className="sr-only">Unread: </span>}
                      {n.title}
                    </span>
                    {n.body && <span className="block text-xs text-slate-700">{n.body}</span>}
                    <span className="block text-xs text-slate-600">{relativeTime(n.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const first = useRef(true);

  // Move focus to the main region after client-side navigation so screen-reader and keyboard users
  // start at the new page's content (the page <h1> is the first thing read).
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    mainRef.current?.focus();
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <div className="min-h-screen lg:flex">
      <a href="#main-content" className="sr-only-focusable fixed left-2 top-2 z-50 rounded bg-white px-4 py-2 font-medium text-navy-900 shadow">
        Skip to main content
      </a>

      <aside className="hidden w-64 shrink-0 flex-col bg-navy-900 lg:flex" aria-label="Sidebar">
        <div className="on-dark px-5 py-5">
          <Brand />
        </div>
        <Sidebar />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-navy-950/60" aria-hidden="true" onClick={() => setMobileOpen(false)} />
          <aside id="mobile-nav" className="relative flex h-full w-72 max-w-[85vw] flex-col bg-navy-900" aria-label="Sidebar">
            <div className="on-dark flex items-center justify-between px-5 py-4">
              <Brand />
              <button type="button" className="rounded p-1 text-white" onClick={() => setMobileOpen(false)} aria-label="Close navigation menu">
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
            <Sidebar onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white/95 px-4 py-2 backdrop-blur sm:px-6">
          <button
            type="button"
            className="rounded-md p-2 text-navy-900 hover:bg-slate-100 lg:hidden"
            aria-expanded={mobileOpen}
            aria-controls="mobile-nav"
            onClick={() => setMobileOpen(true)}
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
            <span className="sr-only">Open navigation menu</span>
          </button>
          <div className="flex-1" />
          <Notifications />
          <div className="hidden text-right sm:block">
            <p className="text-sm font-medium text-navy-900">{user?.full_name || user?.email}</p>
            {user?.full_name && <p className="text-xs text-slate-700">{user.email}</p>}
          </div>
          <button type="button" onClick={() => logout()} className="flex items-center gap-1 rounded-md px-2 py-2 text-sm font-medium text-navy-900 hover:bg-slate-100">
            <LogOut className="h-4 w-4" aria-hidden="true" />
            Sign out
          </button>
        </header>
        <main id="main-content" ref={mainRef} tabIndex={-1} className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 focus:outline-none sm:px-6 lg:px-8">
          <Suspense fallback={<div role="status" className="py-8 text-slate-700">Loading page…</div>}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
