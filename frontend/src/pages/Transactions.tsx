import { Download, Pencil, Plus, Search, Sparkles, Trash2, Upload } from "lucide-react";
import { useCallback, useState } from "react";
import { useSearchParams } from "react-router";

import { QuickAdd } from "../components/QuickAdd";
import { TransactionForm, emptyValues, valuesFrom } from "../components/TransactionForm";
import {
  Button,
  Card,
  Dialog,
  EmptyState,
  ErrorState,
  Input,
  Notice,
  PageHeader,
  Select,
  Skeleton,
  cx,
} from "../components/ui";
import { ApiError, api, errorMessage, getToken } from "../lib/api";
import { useAuth } from "../lib/auth";
import { notifyDataChanged, useOnDataChanged } from "../lib/events";
import { PAYMENT_METHODS, date, signedMoney } from "../lib/format";
import type { Category, Transaction, TransactionPage } from "../lib/types";
import { useApi } from "../lib/useApi";

const PAGE_SIZE = 25;
const FILTER_KEYS = ["q", "type", "category_id", "start", "end", "sort"] as const;

export function Transactions() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const filters = Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) ?? ""])) as Record<(typeof FILTER_KEYS)[number], string>;
  const page = Number(params.get("page") ?? 1) || 1;
  const list = useApi<TransactionPage>("/transactions", { ...filters, page, page_size: PAGE_SIZE });
  const { data: categories } = useApi<Category[]>("/categories");
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [deleting, setDeleting] = useState<Transaction | null>(null);
  const [importing, setImporting] = useState(false);
  const [search, setSearch] = useState(filters.q);
  useOnDataChanged(useCallback(() => void list.reload(), [list.reload]));

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("page");
    setParams(next, { replace: true });
  };
  const goToPage = (n: number) => {
    const next = new URLSearchParams(params);
    next.set("page", String(n));
    setParams(next, { replace: true });
    window.scrollTo({ top: 0 });
  };
  const anyFilter = FILTER_KEYS.some((k) => k !== "sort" && filters[k]);
  const totalPages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1;

  async function exportCsv() {
    const url = new URL((import.meta.env.VITE_API_URL ?? "http://localhost:8000") + "/api/v1/transactions/export");
    for (const [k, v] of Object.entries(filters)) if (v) url.searchParams.set(k, v);
    const res = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } });
    if (!res.ok) return;
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "smartspend-transactions.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <>
      <PageHeader
        title="Transactions"
        description="Every income and expense you've recorded."
        actions={
          <>
            <Button variant="secondary" onClick={() => setImporting(true)}>
              <Upload className="size-4" aria-hidden /> Import CSV
            </Button>
            <Button variant="secondary" onClick={exportCsv}>
              <Download className="size-4" aria-hidden /> Export
            </Button>
            <Button onClick={() => setAdding(true)}>
              <Plus className="size-4" aria-hidden /> Add
            </Button>
          </>
        }
      />

      <Card className="mb-4 p-4">
        <QuickAdd onManual={() => setAdding(true)} />
      </Card>

      {/* Filters: one row above the results */}
      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-[1.4fr_repeat(5,1fr)]">
        <form
          className="relative sm:col-span-2 lg:col-span-1"
          onSubmit={(e) => {
            e.preventDefault();
            setFilter("q", search.trim());
          }}
          role="search"
        >
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" aria-hidden />
          <Input aria-label="Search descriptions and notes" placeholder="Search" value={search} onChange={(e) => setSearch(e.target.value)} onBlur={() => setFilter("q", search.trim())} className="pl-9" />
        </form>
        <Select aria-label="Type" value={filters.type} onChange={(e) => setFilter("type", e.target.value)}>
          <option value="">All types</option>
          <option value="expense">Expenses</option>
          <option value="income">Income</option>
        </Select>
        <Select aria-label="Category" value={filters.category_id} onChange={(e) => setFilter("category_id", e.target.value)}>
          <option value="">All categories</option>
          {(categories ?? [])
            .filter((c) => !filters.type || c.type === filters.type)
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
                {filters.type ? "" : ` (${c.type})`}
              </option>
            ))}
        </Select>
        <Input aria-label="From date" type="date" value={filters.start} onChange={(e) => setFilter("start", e.target.value)} />
        <Input aria-label="To date" type="date" value={filters.end} onChange={(e) => setFilter("end", e.target.value)} />
        <Select aria-label="Sort" value={filters.sort || "date_desc"} onChange={(e) => setFilter("sort", e.target.value === "date_desc" ? "" : e.target.value)}>
          <option value="date_desc">Newest first</option>
          <option value="date_asc">Oldest first</option>
          <option value="amount_desc">Largest first</option>
          <option value="amount_asc">Smallest first</option>
        </Select>
      </div>
      {anyFilter && (
        <div className="mb-3 flex items-center gap-3 text-sm text-muted">
          <span aria-live="polite">{list.data ? `${list.data.total} matching transaction${list.data.total === 1 ? "" : "s"}` : "Filtering…"}</span>
          <button
            className="font-medium text-brand hover:underline"
            onClick={() => {
              setSearch("");
              setParams(new URLSearchParams(), { replace: true });
            }}
          >
            Clear filters
          </button>
        </div>
      )}

      <Card>
        {list.error ? (
          <ErrorState message={list.error} onRetry={list.reload} />
        ) : !list.data ? (
          <div className="space-y-3 p-5">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        ) : list.data.items.length === 0 ? (
          anyFilter ? (
            <EmptyState title="No transactions match these filters">Try a wider date range or clear the filters.</EmptyState>
          ) : (
            <EmptyState title="No transactions yet" action={<Button onClick={() => setAdding(true)}>Add your first one</Button>}>
              Add income and expenses manually, describe them in a sentence, or import a CSV.
            </EmptyState>
          )
        ) : (
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <caption className="sr-only">Transactions</caption>
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th scope="col" className="px-5 py-3 font-medium">Date</th>
                  <th scope="col" className="py-3 font-medium">Description</th>
                  <th scope="col" className="py-3 font-medium">Category</th>
                  <th scope="col" className="py-3 font-medium">Paid with</th>
                  <th scope="col" className="py-3 text-right font-medium">Amount</th>
                  <th scope="col" className="w-24 px-5 py-3"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((t) => (
                  <tr key={t.id} className="border-b border-line/70 last:border-0 hover:bg-canvas/60">
                    <td className="tnum px-5 py-3 whitespace-nowrap text-ink-2">
                      {date(t.transaction_date)}
                      {t.is_future && <span className="ml-1.5 rounded bg-warning-soft px-1.5 py-0.5 text-xs text-warning-ink">Future</span>}
                    </td>
                    <td className="max-w-[260px] py-3">
                      <span className="flex items-center gap-1.5 truncate font-medium text-ink">
                        {t.description}
                        {t.source === "ai" && <Sparkles className="size-3.5 shrink-0 text-brand" aria-label="Added with AI help" />}
                      </span>
                      {t.notes && <span className="block truncate text-xs text-muted">{t.notes}</span>}
                    </td>
                    <td className="py-3 text-ink-2">{t.category.name}</td>
                    <td className="py-3 text-ink-2">{t.payment_method ? PAYMENT_METHODS[t.payment_method] : "—"}</td>
                    <td className={cx("tnum py-3 text-right font-medium whitespace-nowrap", t.type === "income" ? "text-good-ink" : "text-ink")}>
                      {signedMoney(t.amount, t.type, user?.currency)}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex justify-end gap-1">
                        <button className="grid size-8 place-items-center rounded-lg text-muted hover:bg-surface hover:text-ink" onClick={() => setEditing(t)} aria-label={`Edit ${t.description}`}>
                          <Pencil className="size-4" aria-hidden />
                        </button>
                        <button className="grid size-8 place-items-center rounded-lg text-muted hover:bg-critical-soft hover:text-critical-ink" onClick={() => setDeleting(t)} aria-label={`Delete ${t.description}`}>
                          <Trash2 className="size-4" aria-hidden />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {list.data && list.data.total > PAGE_SIZE && (
          <nav aria-label="Pages" className="flex items-center justify-between border-t border-line px-5 py-3 text-sm">
            <span className="text-muted">
              Page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => goToPage(page - 1)}>
                Previous
              </Button>
              <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => goToPage(page + 1)}>
                Next
              </Button>
            </div>
          </nav>
        )}
      </Card>

      <Dialog open={adding} onClose={() => setAdding(false)} title="Add transaction">
        {adding && <TransactionForm initial={emptyValues()} onSaved={() => setAdding(false)} onCancel={() => setAdding(false)} />}
      </Dialog>
      <Dialog open={Boolean(editing)} onClose={() => setEditing(null)} title="Edit transaction">
        {editing && <TransactionForm initial={valuesFrom(editing)} transactionId={editing.id} onSaved={() => setEditing(null)} onCancel={() => setEditing(null)} />}
      </Dialog>
      <DeleteDialog txn={deleting} onClose={() => setDeleting(null)} />
      <ImportDialog open={importing} onClose={() => setImporting(false)} />
    </>
  );
}

function DeleteDialog({ txn, onClose }: { txn: Transaction | null; onClose: () => void }) {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog open={Boolean(txn)} onClose={onClose} title="Delete transaction?">
      {txn && (
        <div className="flex flex-col gap-4">
          {error && <Notice tone="error">{error}</Notice>}
          <p className="text-sm text-ink-2">
            “{txn.description}”, {signedMoney(txn.amount, txn.type, user?.currency)} on {date(txn.transaction_date)}, will be removed and your budgets will
            be recalculated. This can't be undone.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Keep it
            </Button>
            <Button
              variant="danger"
              loading={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await api(`/transactions/${txn.id}`, { method: "DELETE" });
                  notifyDataChanged();
                  onClose();
                } catch (e) {
                  setError(errorMessage(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              Delete
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}

interface Preview {
  valid: { line: number; transaction_date: string; type: string; category: string; description: string; amount: string }[];
  invalid: { line: number; error: string }[];
}

function ImportDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user } = useAuth();
  const [csv, setCsv] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<number | null>(null);

  const reset = () => {
    setCsv(null);
    setPreview(null);
    setError(null);
    setDone(null);
    onClose();
  };

  async function choose(file: File | undefined) {
    if (!file) return;
    setError(null);
    setPreview(null);
    if (file.size > 900_000) return setError("That file is too large. Split it into smaller files (up to 2,000 rows each).");
    const text = await file.text();
    setCsv(text);
    setBusy(true);
    try {
      setPreview(await api<Preview>("/transactions/import/preview", { body: { csv: text } }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't read that file.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onClose={reset} title="Import transactions from CSV" wide>
      <div className="flex flex-col gap-4 text-sm">
        {done !== null ? (
          <>
            <Notice tone="success">Imported {done} transaction{done === 1 ? "" : "s"}.</Notice>
            <div className="flex justify-end">
              <Button onClick={reset}>Done</Button>
            </div>
          </>
        ) : (
          <>
            <p className="text-ink-2">
              Columns: <code className="rounded bg-canvas px-1">date, type, category, description, amount</code> and optionally{" "}
              <code className="rounded bg-canvas px-1">payment_method, notes, currency</code>. Dates as 2026-11-20, type as income or expense, amounts in{" "}
              {user?.currency}. You'll see a preview before anything is saved.
            </p>
            <input type="file" accept=".csv,text/csv" onChange={(e) => choose(e.target.files?.[0])} className="text-sm file:mr-3 file:rounded-lg file:border file:border-line-strong file:bg-surface file:px-3 file:py-1.5 file:text-sm file:font-medium" />
            {busy && <p className="text-muted">Checking the file…</p>}
            {error && <Notice tone="error">{error}</Notice>}
            {preview && (
              <>
                <Notice tone={preview.invalid.length ? "warning" : "success"}>
                  {preview.valid.length} row{preview.valid.length === 1 ? "" : "s"} ready to import
                  {preview.invalid.length > 0 && `, ${preview.invalid.length} with problems (they won't be imported)`}.
                </Notice>
                {preview.invalid.length > 0 && (
                  <ul className="max-h-36 overflow-y-auto rounded-lg border border-line p-3 text-xs">
                    {preview.invalid.map((r) => (
                      <li key={r.line}>
                        Line {r.line}: {r.error}
                      </li>
                    ))}
                  </ul>
                )}
                {preview.valid.length > 0 && (
                  <div className="relative max-h-48 overflow-auto rounded-lg border border-line">
                    <table className="w-full text-xs">
                      <tbody className="tnum">
                        {preview.valid.slice(0, 50).map((r) => (
                          <tr key={r.line} className="border-b border-line/70 last:border-0">
                            <td className="px-3 py-1.5">{r.transaction_date}</td>
                            <td className="py-1.5">{r.description}</td>
                            <td className="py-1.5 text-muted">{r.category}</td>
                            <td className="px-3 py-1.5 text-right">{signedMoney(r.amount, r.type as "income" | "expense", user?.currency)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <div className="flex justify-end gap-2">
                  <Button variant="secondary" onClick={reset}>
                    Cancel
                  </Button>
                  <Button
                    disabled={!preview.valid.length}
                    loading={busy}
                    onClick={async () => {
                      setBusy(true);
                      try {
                        const r = await api<{ imported: number }>("/transactions/import", { body: { csv } });
                        notifyDataChanged();
                        setDone(r.imported);
                      } catch (e) {
                        setError(errorMessage(e));
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Import {preview.valid.length} row{preview.valid.length === 1 ? "" : "s"}
                  </Button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}
