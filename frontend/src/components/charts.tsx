import { useId, useState, type ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { money, moneyCompact, pct } from "../lib/format";
import type { CategoryBreakdown, DailyPoint, MonthlyPoint } from "../lib/types";
import { cx } from "./ui";

const SERIES_1 = "var(--color-series-1)";
const SERIES_2 = "var(--color-series-2)";
const GRID = "var(--color-grid)";
const AXIS = "var(--color-axis)";

/** Every chart has a table view, so no value is only readable by hovering. */
function ChartFrame({ summary, table, children }: { summary: string; table: ReactNode; children: ReactNode }) {
  const [asTable, setAsTable] = useState(false);
  const id = useId();
  return (
    <div>
      <p id={id} className="sr-only">
        {summary}
      </p>
      <div aria-describedby={id}>{asTable ? table : children}</div>
      <div className="mt-2 flex justify-end">
        <button className="text-xs font-medium text-muted underline-offset-2 hover:text-ink hover:underline" onClick={() => setAsTable((t) => !t)}>
          {asTable ? "Show chart" : "Show as table"}
        </button>
      </div>
    </div>
  );
}

function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="mb-3 flex flex-wrap gap-4 text-xs text-ink-2">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: i.color }} aria-hidden />
          {i.label}
        </li>
      ))}
    </ul>
  );
}

function TooltipBox({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-medium text-ink">{title}</p>
      {rows.map((r) => (
        <p key={r.label} className="flex items-center gap-2 text-ink-2">
          {r.color && <span className="size-2 rounded-sm" style={{ background: r.color }} aria-hidden />}
          <span className="flex-1">{r.label}</span>
          <span className="tnum font-medium text-ink">{r.value}</span>
        </p>
      ))}
    </div>
  );
}

function SimpleTable({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <div className="relative overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-muted">
            {head.map((h, i) => (
              <th key={h} className={cx("py-2 font-medium", i > 0 && "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tnum">
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line/70 last:border-0">
              {r.map((c, j) => (
                <td key={j} className={cx("py-2", j > 0 && "text-right")}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- income vs expenses by month

export function IncomeExpenseChart({ data, currency, height = 240 }: { data: MonthlyPoint[]; currency: string; height?: number }) {
  const rows = data.map((d) => ({ ...d, incomeN: Number(d.income), expensesN: Number(d.expenses) }));
  const last = data[data.length - 1];
  const summary = last
    ? `Income and expenses for the last ${data.length} months. ${last.label}: income ${money(last.income, currency)}, expenses ${money(last.expenses, currency)}.`
    : "No data.";
  return (
    <ChartFrame
      summary={summary}
      table={
        <SimpleTable
          head={["Month", "Income", "Expenses", "Net"]}
          rows={data.map((d) => [d.label, money(d.income, currency), money(d.expenses, currency), money(d.net, currency)])}
        />
      }
    >
      <Legend items={[{ label: "Income", color: SERIES_1 }, { label: "Expenses", color: SERIES_2 }]} />
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} barGap={2} barCategoryGap="28%" margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: AXIS }} tickFormatter={(l: string) => l.split(" ")[0]} />
            <YAxis width={56} tickLine={false} axisLine={false} tickFormatter={(v: number) => moneyCompact(v, currency)} />
            <Tooltip
              cursor={{ fill: "var(--color-canvas)" }}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <TooltipBox
                    title={String(label)}
                    rows={[
                      { label: "Income", value: money(payload[0].payload.income, currency), color: SERIES_1 },
                      { label: "Expenses", value: money(payload[0].payload.expenses, currency), color: SERIES_2 },
                      { label: "Net", value: money(payload[0].payload.net, currency) },
                    ]}
                  />
                ) : null
              }
            />
            <Bar dataKey="incomeN" name="Income" fill={SERIES_1} radius={[4, 4, 0, 0]} maxBarSize={28} />
            <Bar dataKey="expensesN" name="Expenses" fill={SERIES_2} radius={[4, 4, 0, 0]} maxBarSize={28} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

// ---------------------------------------------------------------- category breakdown (a ranked bar list)

export function CategoryBars({ data, currency, limit = 6, compare }: { data: CategoryBreakdown; currency: string; limit?: number; compare?: boolean }) {
  const items = data.items.slice(0, limit);
  const rest = data.items.slice(limit);
  const restTotal = rest.reduce((s, i) => s + Number(i.total), 0);
  const max = Math.max(...data.items.map((i) => Number(i.total)), 1);
  const rows = [
    ...items.map((i) => ({ key: String(i.category_id), name: i.name, total: Number(i.total), share: i.share, prev: Number(i.previous_total), count: i.count })),
    ...(rest.length
      ? [{ key: "other", name: `Other (${rest.length})`, total: restTotal, share: String(((restTotal / Number(data.total)) * 100).toFixed(1)), prev: rest.reduce((s, i) => s + Number(i.previous_total), 0), count: rest.reduce((s, i) => s + i.count, 0) }]
      : []),
  ];
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((r) => {
        const change = compare && r.prev > 0 ? ((r.total - r.prev) / r.prev) * 100 : null;
        return (
          <li key={r.key}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
              <span className="truncate text-ink">{r.name}</span>
              <span className="tnum shrink-0 text-ink">
                {money(r.total, currency)} <span className="text-muted">· {pct(r.share)}</span>
              </span>
            </div>
            <div className="h-2 rounded-full bg-canvas" aria-hidden>
              <div className="h-full rounded-full" style={{ width: `${(r.total / max) * 100}%`, background: SERIES_1 }} />
            </div>
            {compare && (
              <p className="tnum mt-1 text-xs text-muted">
                Last month {money(r.prev, currency)}
                {change !== null && ` · ${change >= 0 ? "up" : "down"} ${Math.abs(change).toFixed(0)}%`} · {r.count} transaction{r.count === 1 ? "" : "s"}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

// ---------------------------------------------------------------- spending pace through the month

export function SpendPaceChart({ data, budget, currency, today, height = 220 }: { data: DailyPoint[]; budget: number | null; currency: string; today?: string; height?: number }) {
  const upTo = today ? data.filter((d) => d.date <= today) : data;
  const rows = data.map((d) => ({ day: d.day, date: d.date, cumulative: !today || d.date <= today ? Number(d.cumulative) : null, spent: d.expenses }));
  const last = upTo[upTo.length - 1];
  const maxY = Math.max(budget ?? 0, Number(last?.cumulative ?? 0)) * 1.1 || 1;
  return (
    <ChartFrame
      summary={`Cumulative spending through the month${last ? `, ${money(last.cumulative, currency)} by day ${last.day}` : ""}${budget ? `, against a budget of ${money(budget, currency)}` : ""}.`}
      table={
        <SimpleTable
          head={["Day", "Spent that day", "Running total"]}
          rows={upTo.filter((d) => Number(d.expenses) > 0).map((d) => [d.date, money(d.expenses, currency), money(d.cumulative, currency)])}
        />
      }
    >
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={rows} margin={{ top: 16, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="day" tickLine={false} axisLine={{ stroke: AXIS }} interval="preserveStartEnd" minTickGap={16} />
            <YAxis width={56} tickLine={false} axisLine={false} domain={[0, maxY]} tickFormatter={(v: number) => moneyCompact(v, currency)} />
            {budget ? (
              <ReferenceLine
                y={budget}
                stroke="var(--color-ink-2)"
                strokeWidth={1}
                label={{ value: `Budget ${money(budget, currency)}`, position: "insideTopRight", fill: "var(--color-ink-2)", fontSize: 12 }}
              />
            ) : null}
            <Tooltip
              cursor={{ stroke: AXIS }}
              content={({ active, payload }) =>
                active && payload?.length && payload[0].payload.cumulative !== null ? (
                  <TooltipBox
                    title={`Day ${payload[0].payload.day}`}
                    rows={[
                      { label: "Spent that day", value: money(payload[0].payload.spent, currency) },
                      { label: "Running total", value: money(payload[0].payload.cumulative, currency), color: SERIES_1 },
                    ]}
                  />
                ) : null
              }
            />
            <Area
              type="monotone"
              dataKey="cumulative"
              stroke={SERIES_1}
              strokeWidth={2}
              fill={SERIES_1}
              fillOpacity={0.08}
              connectNulls={false}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--color-surface)" }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}
