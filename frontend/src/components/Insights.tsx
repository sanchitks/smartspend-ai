import { ChevronDown, Lightbulb, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../lib/api";
import { useOnDataChanged } from "../lib/events";
import type { Insight } from "../lib/types";
import { Card, CardHeader, EmptyState, ErrorState, Skeleton } from "./ui";

const EVIDENCE_LABELS: Record<string, string> = {
  period: "Period",
  budget: "Budget",
  spent: "Spent",
  utilisation_percent: "Used (%)",
  days_left: "Days left",
  remaining: "Remaining",
  per_day: "Per day to stay within",
  over_by: "Over by",
  weekly_cap: "Weekly limit",
  current_period_total: "This month so far",
  previous_period_total: "Same days last month",
  change_percent: "Change (%)",
  compared_days: "Days compared",
  count: "Times",
  total: "Total",
  category: "Category",
  half: "Half of total",
  target: "Target",
  saved: "Saved",
  monthly_needed: "Needed per month",
  target_date: "Target date",
  category_total: "Category total",
  share_percent: "Share (%)",
};

export function InsightsPanel() {
  const [items, setItems] = useState<Insight[] | null>(null);
  const [provider, setProvider] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api<{ insights: Insight[]; provider: string }>("/ai/insights", { method: "POST" });
      setItems(r.insights);
      setProvider(r.provider);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  useOnDataChanged(load);

  return (
    <Card>
      <CardHeader
        title="Insights"
        subtitle="Ideas based on your own records. Optional, not advice."
        action={
          <button onClick={load} className="grid size-8 place-items-center rounded-lg text-muted hover:bg-canvas hover:text-ink" aria-label="Refresh insights">
            <RefreshCw className={loading ? "size-4 animate-spin" : "size-4"} aria-hidden />
          </button>
        }
      />
      <div className="px-5 pb-5">
        {error ? (
          <ErrorState message={error} onRetry={load} />
        ) : items === null ? (
          <div className="space-y-3">
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
        ) : items.length === 0 ? (
          <EmptyState icon={<Lightbulb className="size-5" aria-hidden />} title="Nothing to flag yet">
            Add a few transactions and budgets, and observations will show up here.
          </EmptyState>
        ) : (
          <ul className="flex flex-col gap-3">
            {items.map((i) => (
              <InsightItem key={i.id} insight={i} />
            ))}
          </ul>
        )}
        {items && items.length > 0 && (
          <p className="mt-3 text-xs text-muted">{provider === "claude" ? "Worded by Claude; figures calculated by SmartSpend." : "Figures calculated by SmartSpend."}</p>
        )}
      </div>
    </Card>
  );
}

function InsightItem({ insight }: { insight: Insight }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-lg border border-line p-3">
      <p className="text-sm font-medium text-ink">{insight.title}</p>
      <p className="mt-1 text-sm text-ink-2">{insight.summary}</p>
      <p className="mt-2 text-sm text-ink">
        <span className="font-medium">Idea: </span>
        {insight.suggested_action}
      </p>
      <button className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-muted hover:text-ink" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <ChevronDown className={open ? "size-3.5 rotate-180" : "size-3.5"} aria-hidden /> {open ? "Hide" : "Show"} the numbers
      </button>
      {open && (
        <div className="mt-2 rounded-md bg-canvas p-2.5 text-xs">
          <dl className="tnum grid grid-cols-2 gap-x-3 gap-y-1">
            {Object.entries(insight.evidence).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-muted">{EVIDENCE_LABELS[k] ?? k}</dt>
                <dd className="text-right text-ink">{String(v)}</dd>
              </div>
            ))}
          </dl>
          {insight.limitations.length > 0 && <p className="mt-2 text-muted">Note: {insight.limitations.join(" ")}</p>}
        </div>
      )}
    </li>
  );
}
