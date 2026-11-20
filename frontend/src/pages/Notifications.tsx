import { AlertTriangle, Bell, CircleAlert, OctagonAlert } from "lucide-react";
import { Link } from "react-router";

import { Button, Card, EmptyState, ErrorState, PageHeader, Skeleton, cx } from "../components/ui";
import { api } from "../lib/api";
import { notifyDataChanged } from "../lib/events";
import { relativeTime } from "../lib/format";
import type { Notification } from "../lib/types";
import { useApi } from "../lib/useApi";

const ICONS: Record<string, { Icon: typeof Bell; className: string; label: string }> = {
  budget_approaching: { Icon: CircleAlert, className: "bg-warning-soft text-warning-ink", label: "Approaching limit" },
  budget_near_limit: { Icon: AlertTriangle, className: "bg-serious-soft text-serious-ink", label: "Near limit" },
  budget_exceeded: { Icon: OctagonAlert, className: "bg-critical-soft text-critical-ink", label: "Over budget" },
};

export function Notifications() {
  const list = useApi<Notification[]>("/notifications");
  const unread = (list.data ?? []).filter((n) => !n.is_read).length;

  async function markRead(n: Notification) {
    if (n.is_read) return;
    await api(`/notifications/${n.id}/read`, { method: "PATCH" }).catch(() => undefined);
    list.setData((prev) => prev?.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)) ?? prev);
    notifyDataChanged();
  }

  return (
    <>
      <PageHeader
        title="Notifications"
        description="Budget alerts at 75%, 90% and when you go over. Each alert is sent once per budget per month."
        actions={
          unread > 0 && (
            <Button
              variant="secondary"
              onClick={async () => {
                await api("/notifications/read-all", { method: "POST" }).catch(() => undefined);
                await list.reload();
                notifyDataChanged();
              }}
            >
              Mark all as read
            </Button>
          )
        }
      />
      <Card>
        {list.error ? (
          <ErrorState message={list.error} onRetry={list.reload} />
        ) : !list.data ? (
          <div className="space-y-3 p-5">
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </div>
        ) : list.data.length === 0 ? (
          <EmptyState icon={<Bell className="size-5" aria-hidden />} title="You're all caught up">
            When spending reaches 75% of a budget, you'll see an alert here.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-line">
            {list.data.map((n) => {
              const look = ICONS[n.type] ?? { Icon: Bell, className: "bg-canvas text-muted", label: "Notice" };
              const period = typeof n.meta.period === "string" ? n.meta.period : null;
              return (
                <li key={n.id} className={cx("flex gap-3 px-5 py-4", !n.is_read && "bg-brand-soft/40")}>
                  <span className={cx("grid size-9 shrink-0 place-items-center rounded-full", look.className)} title={look.label}>
                    <look.Icon className="size-4" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-ink">
                      {!n.is_read && <span className="sr-only">Unread: </span>}
                      {n.title}
                    </p>
                    <p className="text-sm text-ink-2">{n.message}</p>
                    <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted">
                      <span>{look.label}</span>
                      <span>{relativeTime(n.created_at)}</span>
                      {period && (
                        <Link to={`/app/budgets?year=${period.slice(0, 4)}&month=${Number(period.slice(5, 7))}`} className="font-medium text-brand hover:underline" onClick={() => markRead(n)}>
                          View budget
                        </Link>
                      )}
                      {!n.is_read && (
                        <button className="font-medium text-ink-2 hover:underline" onClick={() => markRead(n)}>
                          Mark as read
                        </button>
                      )}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </>
  );
}
