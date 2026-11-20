import { ArrowDownRight, ArrowUpRight, Plus, ReceiptText, Wallet } from "lucide-react";
import { useCallback, useState } from "react";
import { Link } from "react-router";

import { IncomeExpenseChart, CategoryBars } from "../components/charts";
import { InsightsPanel } from "../components/Insights";
import { QuickAdd } from "../components/QuickAdd";
import { TransactionForm, emptyValues, valuesFrom } from "../components/TransactionForm";
import { TransactionList } from "../components/TransactionList";
import {
  Button,
  Card,
  CardHeader,
  Dialog,
  EmptyState,
  ErrorState,
  MonthPicker,
  PageHeader,
  ProgressBar,
  Skeleton,
  StatusBadge,
  cx,
} from "../components/ui";
import { useAuth } from "../lib/auth";
import { useOnDataChanged } from "../lib/events";
import { money, pct } from "../lib/format";
import type { BudgetSummary, CategoryBreakdown, MonthlyPoint, Overview, Transaction } from "../lib/types";
import { useApi } from "../lib/useApi";

function currentMonth() {
  const d = new Date();
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

export function Dashboard() {
  const { user } = useAuth();
  const now = currentMonth();
  const [{ year, month }, setPeriod] = useState(now);
  const q = { year, month };
  const overview = useApi<Overview>("/analytics/overview", q);
  const monthly = useApi<{ items: MonthlyPoint[] }>("/analytics/monthly", { ...q, months: 6 });
  const cats = useApi<CategoryBreakdown>("/analytics/categories", q);
  const budgets = useApi<BudgetSummary>("/budgets", q);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const cur = user?.currency ?? "INR";

  const reloadAll = useCallback(() => {
    void overview.reload();
    void monthly.reload();
    void cats.reload();
    void budgets.reload();
  }, [overview.reload, monthly.reload, cats.reload, budgets.reload]);
  useOnDataChanged(reloadAll);

  const o = overview.data;
  const firstName = user?.name.split(" ")[0];

  return (
    <>
      <PageHeader
        title={`Hello, ${firstName}`}
        description={o ? (o.is_current_month ? `Here's ${o.label} so far: day ${o.days_elapsed} of ${o.days_in_month}.` : `Here's ${o.label}.`) : " "}
        actions={
          <>
            <MonthPicker year={year} month={month} onChange={(y, m) => setPeriod({ year: y, month: m })} max={now} />
            <Button onClick={() => setAdding(true)}>
              <Plus className="size-4" aria-hidden /> Add transaction
            </Button>
          </>
        }
      />

      <Card className="mb-6 p-4">
        <QuickAdd onManual={() => setAdding(true)} />
      </Card>

      {overview.error ? (
        <Card>
          <ErrorState message={overview.error} onRetry={overview.reload} />
        </Card>
      ) : (
        <>
          <SummaryCards o={o} currency={cur} />

          {o && !o.has_any_transactions ? (
            <Card className="mt-6">
              <EmptyState
                icon={<ReceiptText className="size-5" aria-hidden />}
                title="Add your first transaction"
                action={
                  <Button onClick={() => setAdding(true)}>
                    <Plus className="size-4" aria-hidden /> Add manually
                  </Button>
                }
              >
                Type something like “spent ₹200 on groceries” in the box above, or add one manually. Charts and insights
                appear as soon as you have records.
              </EmptyState>
            </Card>
          ) : (
            <div className="mt-6 grid items-start gap-6 lg:grid-cols-5">
              <Card className="lg:col-span-3">
                <CardHeader title="Income vs expenses" subtitle="Last 6 months" />
                <div className="px-5 pb-4">
                  {monthly.data ? <IncomeExpenseChart data={monthly.data.items} currency={cur} /> : <Skeleton className="h-60" />}
                </div>
              </Card>
              <Card className="lg:col-span-2">
                <CardHeader
                  title="Spending by category"
                  subtitle={o?.label}
                  action={
                    <Link to="/app/analytics" className="text-sm font-medium text-brand hover:underline">
                      Details
                    </Link>
                  }
                />
                <div className="px-5 pb-5">
                  {!cats.data ? (
                    <Skeleton className="h-48" />
                  ) : cats.data.items.length === 0 ? (
                    <p className="py-8 text-center text-sm text-muted">No expenses this month.</p>
                  ) : (
                    <CategoryBars data={cats.data} currency={cur} limit={5} />
                  )}
                </div>
              </Card>

              <Card className="lg:col-span-3">
                <CardHeader
                  title="Budgets"
                  subtitle={o?.label}
                  action={
                    <Link to={`/app/budgets?year=${year}&month=${month}`} className="text-sm font-medium text-brand hover:underline">
                      Manage
                    </Link>
                  }
                />
                <BudgetPreview summary={budgets.data} currency={cur} />
              </Card>
              <div className="lg:col-span-2">
                <InsightsPanel />
              </div>

              <Card className="lg:col-span-5">
                <CardHeader
                  title="Recent transactions"
                  action={
                    <Link to="/app/transactions" className="text-sm font-medium text-brand hover:underline">
                      View all
                    </Link>
                  }
                />
                {o ? <TransactionList items={o.recent} onSelect={setEditing} /> : <Skeleton className="mx-5 mb-5 h-40" />}
              </Card>
            </div>
          )}
        </>
      )}

      <Dialog open={adding} onClose={() => setAdding(false)} title="Add transaction">
        {adding && <TransactionForm initial={emptyValues()} onSaved={() => setAdding(false)} onCancel={() => setAdding(false)} />}
      </Dialog>
      <Dialog open={Boolean(editing)} onClose={() => setEditing(null)} title="Edit transaction">
        {editing && <TransactionForm initial={valuesFrom(editing)} transactionId={editing.id} onSaved={() => setEditing(null)} onCancel={() => setEditing(null)} />}
      </Dialog>
    </>
  );
}

function SummaryCards({ o, currency }: { o: Overview | null; currency: string }) {
  if (!o) {
    return (
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
    );
  }
  const change = Number(o.comparison.change);
  const cards = [
    { label: "Income", value: money(o.income, currency), foot: `${o.transaction_count} transactions this month` },
    {
      label: "Expenses",
      value: money(o.expenses, currency),
      foot:
        o.comparison.change_percent === null ? (
          "No spending to compare with yet"
        ) : (
          <span className="inline-flex items-center gap-1" title={o.comparison.note}>
            {change > 0 ? <ArrowUpRight className="size-3.5" aria-hidden /> : <ArrowDownRight className="size-3.5" aria-hidden />}
            {pct(Math.abs(Number(o.comparison.change_percent)))} {change > 0 ? "more" : "less"} than {o.comparison.label}
          </span>
        ),
    },
    {
      label: "Net cash flow",
      value: money(o.net, currency),
      foot: Number(o.net) >= 0 ? "Income minus expenses" : "You spent more than you earned",
      tone: Number(o.net) < 0 ? "text-critical-ink" : undefined,
    },
    {
      label: "Budget remaining",
      value: o.budget_remaining === null ? "No budget set" : money(o.budget_remaining, currency),
      foot: o.budget === null ? (
        <Link to="/app/budgets" className="font-medium text-brand hover:underline">
          Set a monthly budget
        </Link>
      ) : (
        `${pct(o.budget_utilisation)} of ${money(o.budget, currency)} used`
      ),
      tone: o.budget_remaining !== null && Number(o.budget_remaining) < 0 ? "text-critical-ink" : undefined,
      small: o.budget_remaining === null,
    },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {cards.map((c) => (
        <Card key={c.label} as="div" className="p-4">
          <p className="text-sm text-muted">{c.label}</p>
          <p className={cx("mt-1 font-semibold tracking-tight", c.small ? "text-lg text-muted" : "text-2xl", c.tone ?? "text-ink")}>{c.value}</p>
          <p className="mt-1 text-xs text-muted">{c.foot}</p>
        </Card>
      ))}
    </div>
  );
}

function BudgetPreview({ summary, currency }: { summary: BudgetSummary | null; currency: string }) {
  if (!summary) return <Skeleton className="mx-5 mb-5 h-40" />;
  const rows = [...(summary.total ? [summary.total] : []), ...summary.categories].slice(0, 5);
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<Wallet className="size-5" aria-hidden />}
        title="No budgets this month"
        action={
          <Link to="/app/budgets" className="rounded-lg border border-line-strong px-3 py-1.5 text-sm font-medium hover:bg-canvas">
            Create a budget
          </Link>
        }
      >
        Set a monthly total or limits for categories like Food &amp; Dining.
      </EmptyState>
    );
  }
  return (
    <ul className="flex flex-col gap-4 px-5 pb-5">
      {rows.map((b) => {
        const name = b.category?.name ?? "Total monthly budget";
        return (
          <li key={b.id}>
            <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2 text-sm">
              <span className="font-medium text-ink">{name}</span>
              <StatusBadge status={b.status} />
            </div>
            <ProgressBar value={b.utilisation === null ? null : Number(b.utilisation)} status={b.status} label={`${name} budget used`} />
            <p className="tnum mt-1 text-xs text-muted">
              {money(b.spent, currency)} of {money(b.amount, currency)} ·{" "}
              {Number(b.remaining) >= 0 ? `${money(b.remaining, currency)} left` : `${money(-Number(b.remaining), currency)} over`}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
