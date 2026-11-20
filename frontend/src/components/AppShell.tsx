import {
  ArrowLeftRight,
  BarChart3,
  Bell,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareText,
  Settings,
  Target,
  Wallet,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useOnDataChanged } from "../lib/events";
import type { Notification } from "../lib/types";
import { Logo } from "./Logo";
import { cx } from "./ui";

const NAV = [
  { to: "/app", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/app/transactions", label: "Transactions", icon: ArrowLeftRight },
  { to: "/app/budgets", label: "Budgets", icon: Wallet },
  { to: "/app/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/app/assistant", label: "AI Assistant", icon: MessageSquareText },
  { to: "/app/goals", label: "Savings Goals", icon: Target },
  { to: "/app/notifications", label: "Notifications", icon: Bell },
  { to: "/app/settings", label: "Profile & Settings", icon: Settings },
];

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [unread, setUnread] = useState(0);

  const loadUnread = useCallback(() => {
    api<Notification[]>("/notifications", { query: { unread_only: true, limit: 99 } })
      .then((n) => setUnread(n.length))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    loadUnread();
    setMenuOpen(false);
  }, [location.pathname, loadUnread]);
  useOnDataChanged(loadUnread);

  const nav = (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            cx(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              isActive ? "bg-brand-soft text-brand" : "text-ink-2 hover:bg-canvas hover:text-ink",
            )
          }
        >
          <Icon className="size-[18px] shrink-0" aria-hidden />
          <span className="flex-1">{label}</span>
          {to === "/app/notifications" && unread > 0 && (
            <span className="tnum rounded-full bg-critical px-1.5 text-xs font-semibold text-white" aria-label={`${unread} unread`}>
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );

  const account = (
    <div className="border-t border-line pt-3">
      <div className="px-3 pb-2">
        <p className="truncate text-sm font-medium text-ink">{user?.name}</p>
        <p className="truncate text-xs text-muted">{user?.email}</p>
      </div>
      <button
        onClick={async () => {
          await logout();
          navigate("/login");
        }}
        className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-ink-2 hover:bg-canvas"
      >
        <LogOut className="size-[18px]" aria-hidden /> Log out
      </button>
    </div>
  );

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[248px_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-dvh flex-col gap-6 border-r border-line bg-surface px-3 py-5 lg:flex">
        <div className="px-3">
          <Logo />
        </div>
        <div className="flex-1 overflow-y-auto">{nav}</div>
        {account}
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-surface px-4 lg:hidden">
        <Logo />
        <button
          className="relative grid size-10 place-items-center rounded-lg hover:bg-canvas"
          onClick={() => setMenuOpen(true)}
          aria-label="Open menu"
          aria-expanded={menuOpen}
        >
          <Menu className="size-5" aria-hidden />
          {unread > 0 && <span className="absolute top-2 right-2 size-2 rounded-full bg-critical" aria-hidden />}
        </button>
      </header>
      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setMenuOpen(false)} />
          <div className="absolute inset-y-0 right-0 flex w-72 max-w-[85vw] flex-col gap-4 bg-surface px-3 py-4 shadow-xl">
            <div className="flex items-center justify-between px-3">
              <span className="text-sm font-semibold">Menu</span>
              <button className="grid size-9 place-items-center rounded-lg hover:bg-canvas" onClick={() => setMenuOpen(false)} aria-label="Close menu">
                <X className="size-5" aria-hidden />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">{nav}</div>
            {account}
          </div>
        </div>
      )}

      <main id="main" className="min-w-0 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
