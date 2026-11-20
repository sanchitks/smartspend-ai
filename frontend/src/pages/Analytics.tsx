import { useState } from "react";

import { CategoryBars, IncomeExpenseChart, SpendPaceChart } from "../components/charts";
import { Card, CardHeader, ErrorState, MonthPicker, PageHeader, Select, Skeleton } from "../components/ui";
import { useAuth } from "../lib/auth";
import { isoToday, money, pct } from "../lib/format";
import type { BudgetSummary, CategoryBreakdown, DailyPoint, MonthlyPoint, Overview } from "../lib/types";
import { useApi } from "../lib/useApi";

export function Analytics() {
  const { user } = useAuth();
  const cur = user?.currency ?? "INR";
  const now = new Date();
  const max = { year: now.getFullYear(), month: now.getMonth() + 1 };
  const [{ year, month }, setPeriod] = useState(max);
  const [months, setMonths] = useState(6);
  const [kind, setKind] = useState<"expense" | "income">("expense");
  const q = { year, month };
  const overview = useApi<Overview>("/analytics/overview", q);
  const monthly = useApi<{ items: MonthlyPoint[] }>("/analytics/monthly", { ...q, months });
  const cats = useApi<CategoryBreakdown>("/analytics/categories", { ...q, type: kind });
  const daily = useApi<{ items: DailyPoint[] }>("/analytics/daily", q);
  const budgets = useApi<BudgetSummary>("/budgets", q);
  const o = overview.data;
  const isCurrent = year === max.year && month === max.month;

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Trends, category breakdowns and month-to-month comparisons."
        actions={
          <>
            <MonthPicker year={year} month={month} onChange={(y, m) => setPeriod({ year: y, month: m })} max={max} />
            <Select aria-label="Trend length" value={months} onChange={(e) => setMonths(Number(e.target.value))} className="w-auto!">
              <option value={6}>Last 6 months</option>
              <option value={12}>Last 12 months</option>
            </Select>
          </>
        }
      />

      {overview.error ? (
        <Card>
          <ErrorState message={overview.error} onRetry={overview.reload} />
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card className="lg:col-span-2">
            <CardHeader title="Compared with last month" subtitle={o?.comparison.note} />
            <div className="grid grid-cols-2 gap-4 px-5 pb-5 sm:grid-cols-4">
              {o ? (
                <>
                  <Stat label={`Spent in ${o.label}${o.is_current_month ? " so far" : ""}`} value={money(o.expenses, cur)} />
                  <Stat label={`Spent in ${o.comparison.label}`} value={money(o.comparison.expenses, cur)} />
                  <Stat
                    label="Difference"
                    value={`${Number(o.comparison.change) > 0 ? "+" : Number(o.comparison.change) < 0 ? "−" : ""}${money(Math.abs(Number(o.comparison.change)), cur)}`}
                  />
                  <Stat label="Change" value={o.comparison.change_percent === null ? "Not enough data" : pct(o.comparison.change_percent)} />
                </>
              ) : (
                [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)
              )}
            </div>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader title="Income vs expenses" subtitle={`Last ${months} months`} />
            <div className="px-5 pb-4">{monthly.data ? <IncomeExpenseChart data={monthly.data.items} currency={cur} height={280} /> : <Skeleton className="h-72" />}</div>
          </Card>

          <Card>
            <CardHeader
              title={kind === "expense" ? "Spending by category" : "Income by category"}
              subtitle={o?.label}
              action={
                <Select aria-label="Show" value={kind} onChange={(e) => setKind(e.target.value as "expense" | "income")} className="h-8! w-auto! text-xs!">
                  <option value="expense">Expenses</option>
                  <option value="income">Income</option>
                </Select>
              }
            />
            <div className="px-5 pb-5">
              {!cats.data ? (
                <Skeleton className="h-56" />
              ) : cats.data.items.length === 0 ? (
                <p className="py-10 text-center text-sm text-muted">Nothing recorded for this month.</p>
              ) : (
                <CategoryBars data={cats.data} currency={cur} limit={8} compare />
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Spending pace" subtitle={isCurrent ? "Running total this month, against your total budget" : "Running total through the month"} />
            <div className="px-5 pb-4">
              {daily.data ? (
                <SpendPaceChart data={daily.data.items} budget={budgets.data?.total ? Number(budgets.data.total.amount) : null} currency={cur} today={isCurrent ? isoToday() : undefined} />
              ) : (
                <Skeleton className="h-56" />
              )}
              {budgets.data && !budgets.data.total && <p className="mt-2 text-xs text-muted">Set a total monthly budget to see it as a line on this chart.</p>}
            </div>
          </Card>
        </div>
      )}
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold tracking-tight text-ink">{value}</p>
    </div>
  );
}
