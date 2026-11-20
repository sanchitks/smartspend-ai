import { Copy, Pencil, Plus, Trash2, Wallet } from "lucide-react";
import { useCallback, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import {
  Button,
  Card,
  CardHeader,
  Dialog,
  EmptyState,
  ErrorState,
  Field,
  MoneyInput,
  MonthPicker,
  Notice,
  PageHeader,
  ProgressBar,
  Select,
  Skeleton,
  StatusBadge,
  symbolFor,
} from "../components/ui";
import { ApiError, api, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { notifyDataChanged, useOnDataChanged } from "../lib/events";
import { money, monthLabel, pct } from "../lib/format";
import type { Budget, BudgetSummary, Category } from "../lib/types";
import { useApi } from "../lib/useApi";

function lastDay(year: number, month: number) {
  return new Date(year, month, 0).getDate();
}

export function Budgets() {
  const { user } = useAuth();
  const cur = user?.currency ?? "INR";
  const [params, setParams] = useSearchParams();
  const now = new Date();
  const year = Number(params.get("year")) || now.getFullYear();
  const month = Number(params.get("month")) || now.getMonth() + 1;
  const summary = useApi<BudgetSummary>("/budgets", { year, month });
  const { data: categories } = useApi<Category[]>("/categories", { type: "expense" });
  const [editor, setEditor] = useState<{ budget?: Budget; total?: boolean } | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  useOnDataChanged(useCallback(() => void summary.reload(), [summary.reload]));

  const s = summary.data;
  const used = new Set(s?.categories.map((b) => b.category?.id));
  const available = (categories ?? []).filter((c) => !used.has(c.id));
  const monthRange = `start=${year}-${String(month).padStart(2, "0")}-01&end=${year}-${String(month).padStart(2, "0")}-${lastDay(year, month)}`;

  async function copyPrevious() {
    setMessage(null);
    try {
      const r = await api<{ created: number }>("/budgets/copy-previous", { body: { year, month } });
      setMessage({ tone: "success", text: `Copied ${r.created} budget${r.created === 1 ? "" : "s"} from last month.` });
      notifyDataChanged();
    } catch (e) {
      setMessage({ tone: "error", text: errorMessage(e) });
    }
  }

  return (
    <>
      <PageHeader
        title="Budgets"
        description="Monthly limits, checked against what you actually spend."
        actions={<MonthPicker year={year} month={month} onChange={(y, m) => setParams({ year: String(y), month: String(m) }, { replace: true })} />}
      />
      {message && (
        <div className="mb-4">
          <Notice tone={message.tone}>{message.text}</Notice>
        </div>
      )}

      {summary.error ? (
        <Card>
          <ErrorState message={summary.error} onRetry={summary.reload} />
        </Card>
      ) : !s ? (
        <Skeleton className="h-64 rounded-xl" />
      ) : (
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader title="Total monthly budget" subtitle={monthLabel(year, month)} />
            <div className="px-5 pb-5">
              {s.total ? (
                <BudgetRow budget={s.total} currency={cur} name="All spending" onEdit={() => setEditor({ budget: s.total!, total: true })} link={`/app/transactions?type=expense&${monthRange}`} big />
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-canvas px-4 py-3">
                  <p className="text-sm text-ink-2">
                    No total budget for {monthLabel(year, month)}. You've spent {money(s.total_expenses, cur)} so far.
                  </p>
                  <Button size="sm" onClick={() => setEditor({ total: true })}>
                    Set total budget
                  </Button>
                </div>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Category budgets"
              subtitle={s.categories.length ? `${s.categories.length} categor${s.categories.length === 1 ? "y" : "ies"}` : undefined}
              action={
                <div className="flex gap-2">
                  {s.categories.length === 0 && !s.total && (
                    <Button variant="secondary" size="sm" onClick={copyPrevious}>
                      <Copy className="size-4" aria-hidden /> Copy last month
                    </Button>
                  )}
                  <Button size="sm" onClick={() => setEditor({})} disabled={!available.length}>
                    <Plus className="size-4" aria-hidden /> Add
                  </Button>
                </div>
              }
            />
            <div className="px-5 pb-5">
              {s.categories.length === 0 ? (
                <EmptyState icon={<Wallet className="size-5" aria-hidden />} title="No category budgets yet">
                  Limits for categories you want to watch, like Food &amp; Dining or Shopping. You'll get an alert at 75%, 90% and when
                  you go over.
                </EmptyState>
              ) : (
                <ul className="flex flex-col divide-y divide-line">
                  {s.categories.map((b) => (
                    <li key={b.id} className="py-4 first:pt-0 last:pb-0">
                      <BudgetRow
                        budget={b}
                        currency={cur}
                        name={b.category!.name}
                        onEdit={() => setEditor({ budget: b })}
                        link={`/app/transactions?type=expense&category_id=${b.category!.id}&${monthRange}`}
                      />
                    </li>
                  ))}
                </ul>
              )}
              {Number(s.unbudgeted_expenses) > 0 && s.categories.length > 0 && (
                <p className="mt-4 border-t border-line pt-3 text-sm text-muted">
                  {money(s.unbudgeted_expenses, cur)} was spent in categories without their own budget.
                </p>
              )}
            </div>
          </Card>
        </div>
      )}

      <Dialog open={Boolean(editor)} onClose={() => setEditor(null)} title={editor?.budget ? "Edit budget" : editor?.total ? "Set total budget" : "Add category budget"}>
        {editor && (
          <BudgetForm
            year={year}
            month={month}
            budget={editor.budget}
            total={editor.total}
            categories={available}
            currency={cur}
            onDone={() => {
              setEditor(null);
              notifyDataChanged();
            }}
            onCancel={() => setEditor(null)}
          />
        )}
      </Dialog>
    </>
  );
}

function BudgetRow({ budget: b, currency, name, onEdit, link, big }: { budget: Budget; currency: string; name: string; onEdit: () => void; link: string; big?: boolean }) {
  const over = Number(b.remaining) < 0;
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Link to={link} className="font-medium text-ink hover:text-brand hover:underline">
            {name}
          </Link>
          <StatusBadge status={b.status} />
        </div>
        <button onClick={onEdit} className="grid size-8 place-items-center rounded-lg text-muted hover:bg-canvas hover:text-ink" aria-label={`Edit ${name} budget`}>
          <Pencil className="size-4" aria-hidden />
        </button>
      </div>
      <ProgressBar value={b.utilisation === null ? null : Number(b.utilisation)} status={b.status} label={`${name} budget used`} />
      <dl className={`tnum mt-2 grid grid-cols-3 gap-2 ${big ? "text-sm" : "text-xs"}`}>
        <div>
          <dt className="text-muted">Spent</dt>
          <dd className="font-medium text-ink">{money(b.spent, currency)}</dd>
        </div>
        <div>
          <dt className="text-muted">{over ? "Over by" : "Remaining"}</dt>
          <dd className={over ? "font-medium text-critical-ink" : "font-medium text-ink"}>{money(Math.abs(Number(b.remaining)), currency)}</dd>
        </div>
        <div className="text-right">
          <dt className="text-muted">Budget · used</dt>
          <dd className="font-medium text-ink">
            {money(b.amount, currency)} · {pct(b.utilisation)}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function BudgetForm({ year, month, budget, total, categories, currency, onDone, onCancel }: {
  year: number;
  month: number;
  budget?: Budget;
  total?: boolean;
  categories: Category[];
  currency: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [amount, setAmount] = useState(budget?.amount ?? "");
  const [categoryId, setCategoryId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const clean = amount.replace(/,/g, "").trim();
    if (!/^\d+(\.\d{1,2})?$/.test(clean) || Number(clean) <= 0) return setError("Enter an amount greater than zero, with up to 2 decimal places.");
    if (!budget && !total && !categoryId) return setError("Choose a category.");
    setBusy(true);
    setError(null);
    try {
      if (budget) await api(`/budgets/${budget.id}`, { method: "PATCH", body: { amount: clean } });
      else await api("/budgets", { body: { category_id: total ? null : Number(categoryId), amount: clean, year, month } });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save the budget.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      {error && <Notice tone="error">{error}</Notice>}
      <p className="text-sm text-muted">For {monthLabel(year, month)}.</p>
      {!budget && !total && (
        <Field label="Category" htmlFor="budget-category">
          <Select id="budget-category" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">Choose a category</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
      )}
      <Field label="Monthly limit" htmlFor="budget-amount">
        <MoneyInput id="budget-amount" currencySymbol={symbolFor(currency)} value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus />
      </Field>
      <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:items-center">
        {budget &&
          (confirmDelete ? (
            <Button
              type="button"
              variant="danger"
              onClick={async () => {
                await api(`/budgets/${budget.id}`, { method: "DELETE" }).catch(() => undefined);
                onDone();
              }}
            >
              Yes, remove this budget
            </Button>
          ) : (
            <Button type="button" variant="ghost" onClick={() => setConfirmDelete(true)}>
              <Trash2 className="size-4" aria-hidden /> Remove
            </Button>
          ))}
        <div className="flex flex-col-reverse gap-2 sm:ml-auto sm:flex-row">
          <Button type="button" variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" loading={busy}>
            Save budget
          </Button>
        </div>
      </div>
    </form>
  );
}
