import { CheckCircle2, Pencil, Plus, Target } from "lucide-react";
import { useState, type FormEvent } from "react";

import {
  Button,
  Card,
  Dialog,
  EmptyState,
  ErrorState,
  Field,
  Input,
  MoneyInput,
  Notice,
  PageHeader,
  Skeleton,
  symbolFor,
} from "../components/ui";
import { ApiError, api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { date, money, pct } from "../lib/format";
import type { Goal } from "../lib/types";
import { useApi } from "../lib/useApi";

export function Goals() {
  const { user } = useAuth();
  const cur = user?.currency ?? "INR";
  const goals = useApi<Goal[]>("/savings-goals");
  const [editing, setEditing] = useState<Goal | "new" | null>(null);
  const [adding, setAdding] = useState<Goal | null>(null);

  const active = (goals.data ?? []).filter((g) => g.status === "active");
  const done = (goals.data ?? []).filter((g) => g.status !== "active");

  return (
    <>
      <PageHeader
        title="Savings goals"
        description="Track what you're saving towards. Tracking only: SmartSpend doesn't hold or move money."
        actions={
          <Button onClick={() => setEditing("new")}>
            <Plus className="size-4" aria-hidden /> New goal
          </Button>
        }
      />
      {goals.error ? (
        <Card>
          <ErrorState message={goals.error} onRetry={goals.reload} />
        </Card>
      ) : !goals.data ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-40 rounded-xl" />
          <Skeleton className="h-40 rounded-xl" />
        </div>
      ) : goals.data.length === 0 ? (
        <Card>
          <EmptyState icon={<Target className="size-5" aria-hidden />} title="No savings goals yet" action={<Button onClick={() => setEditing("new")}>Create a goal</Button>}>
            An emergency fund, a laptop or a trip. Add a target date and SmartSpend works out how much to set aside each month.
          </EmptyState>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            {active.map((g) => (
              <GoalCard key={g.id} goal={g} currency={cur} onEdit={() => setEditing(g)} onAdd={() => setAdding(g)} />
            ))}
          </div>
          {done.length > 0 && (
            <>
              <h2 className="mt-8 mb-3 text-sm font-semibold text-ink-2">Completed and archived</h2>
              <div className="grid gap-4 md:grid-cols-2">
                {done.map((g) => (
                  <GoalCard key={g.id} goal={g} currency={cur} onEdit={() => setEditing(g)} />
                ))}
              </div>
            </>
          )}
        </>
      )}

      <Dialog open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "New savings goal" : "Edit goal"}>
        {editing !== null && (
          <GoalForm
            goal={editing === "new" ? undefined : editing}
            currency={cur}
            onDone={() => {
              setEditing(null);
              void goals.reload();
            }}
            onCancel={() => setEditing(null)}
          />
        )}
      </Dialog>
      <Dialog open={adding !== null} onClose={() => setAdding(null)} title="Add to savings">
        {adding && (
          <AddMoney
            goal={adding}
            currency={cur}
            onDone={() => {
              setAdding(null);
              void goals.reload();
            }}
          />
        )}
      </Dialog>
    </>
  );
}

function GoalCard({ goal: g, currency, onEdit, onAdd }: { goal: Goal; currency: string; onEdit: () => void; onAdd?: () => void }) {
  const complete = g.status === "completed";
  return (
    <Card as="article" className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-ink">{g.title}</h3>
          <p className="text-xs text-muted">{g.target_date ? `By ${date(g.target_date)}` : "No target date"}</p>
        </div>
        <button onClick={onEdit} className="grid size-8 place-items-center rounded-lg text-muted hover:bg-canvas hover:text-ink" aria-label={`Edit ${g.title}`}>
          <Pencil className="size-4" aria-hidden />
        </button>
      </div>
      <p className="mt-4 text-2xl font-semibold tracking-tight">
        {money(g.current_amount, currency)} <span className="text-sm font-normal text-muted">of {money(g.target_amount, currency)}</span>
      </p>
      <div
        className="mt-2 h-2 overflow-hidden rounded-full bg-canvas ring-1 ring-line ring-inset"
        role="progressbar"
        aria-label={`${g.title} progress`}
        aria-valuenow={Number(g.progress)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="h-full rounded-full bg-brand" style={{ width: `${g.progress}%` }} />
      </div>
      <p className="mt-2 text-xs text-muted">
        {complete ? (
          <span className="inline-flex items-center gap-1 text-good-ink">
            <CheckCircle2 className="size-3.5" aria-hidden /> Goal reached
          </span>
        ) : (
          <>
            {pct(g.progress)} saved · {money(g.remaining, currency)} to go
            {g.monthly_needed && ` · about ${money(g.monthly_needed, currency)} a month`}
          </>
        )}
        {g.status === "archived" && " · Archived"}
      </p>
      {onAdd && (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onAdd}>
          <Plus className="size-4" aria-hidden /> Add money saved
        </Button>
      )}
    </Card>
  );
}

const isAmount = (s: string, allowZero = false) => /^\d+(\.\d{1,2})?$/.test(s) && (allowZero || Number(s) > 0);

function GoalForm({ goal, currency, onDone, onCancel }: { goal?: Goal; currency: string; onDone: () => void; onCancel: () => void }) {
  const [title, setTitle] = useState(goal?.title ?? "");
  const [target, setTarget] = useState(goal?.target_amount ?? "");
  const [saved, setSaved] = useState(goal?.current_amount ?? "0");
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim()) return setError("Give the goal a name.");
    if (!isAmount(target.replace(/,/g, ""))) return setError("Enter a target amount greater than zero.");
    if (!isAmount(saved.replace(/,/g, ""), true)) return setError("Enter how much you've saved so far (0 is fine).");
    setBusy(true);
    setError(null);
    const body = { title: title.trim(), target_amount: target.replace(/,/g, ""), current_amount: saved.replace(/,/g, ""), target_date: targetDate || null };
    try {
      if (goal) await api(`/savings-goals/${goal.id}`, { method: "PATCH", body });
      else await api("/savings-goals", { body });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save the goal.");
    } finally {
      setBusy(false);
    }
  }

  async function setStatus(status: "archived" | "active") {
    await api(`/savings-goals/${goal!.id}`, { method: "PATCH", body: { status } }).catch(() => undefined);
    onDone();
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      {error && <Notice tone="error">{error}</Notice>}
      <Field label="Goal" htmlFor="goal-title">
        <Input id="goal-title" value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Emergency fund" autoFocus />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Target amount" htmlFor="goal-target">
          <MoneyInput id="goal-target" currencySymbol={symbolFor(currency)} value={target} onChange={(e) => setTarget(e.target.value)} />
        </Field>
        <Field label="Saved so far" htmlFor="goal-saved">
          <MoneyInput id="goal-saved" currencySymbol={symbolFor(currency)} value={saved} onChange={(e) => setSaved(e.target.value)} />
        </Field>
      </div>
      <Field label="Target date (optional)" htmlFor="goal-date">
        <Input id="goal-date" type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
      </Field>
      <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:items-center">
        {goal && (
          <div className="flex gap-2">
            <Button type="button" variant="ghost" onClick={() => setStatus(goal.status === "archived" ? "active" : "archived")}>
              {goal.status === "archived" ? "Restore" : "Archive"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="text-critical-ink"
              onClick={async () => {
                if (!window.confirm(`Delete “${goal.title}”? This can't be undone.`)) return;
                await api(`/savings-goals/${goal.id}`, { method: "DELETE" }).catch(() => undefined);
                onDone();
              }}
            >
              Delete
            </Button>
          </div>
        )}
        <div className="flex flex-col-reverse gap-2 sm:ml-auto sm:flex-row">
          <Button type="button" variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" loading={busy}>
            Save goal
          </Button>
        </div>
      </div>
    </form>
  );
}

function AddMoney({ goal, currency, onDone }: { goal: Goal; currency: string; onDone: () => void }) {
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={async (e) => {
        e.preventDefault();
        const clean = amount.replace(/,/g, "");
        if (!isAmount(clean)) return setError("Enter an amount greater than zero.");
        setBusy(true);
        // Add in cents so no floating-point rounding creeps in.
        const toCents = (s: string) => {
          const [w, f = ""] = s.split(".");
          return BigInt(w) * 100n + BigInt((f + "00").slice(0, 2));
        };
        const total = toCents(goal.current_amount) + toCents(clean);
        const next = `${total / 100n}.${String(total % 100n).padStart(2, "0")}`;
        try {
          await api(`/savings-goals/${goal.id}`, { method: "PATCH", body: { current_amount: next } });
          onDone();
        } catch (err) {
          setError(err instanceof ApiError ? err.message : "Couldn't update the goal.");
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <Notice tone="error">{error}</Notice>}
      <p className="text-sm text-muted">
        {goal.title}: {money(goal.current_amount, currency)} of {money(goal.target_amount, currency)} saved.
      </p>
      <Field label="Amount you set aside" htmlFor="add-amount">
        <MoneyInput id="add-amount" currencySymbol={symbolFor(currency)} value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus />
      </Field>
      <div className="flex justify-end">
        <Button type="submit" loading={busy}>
          Update progress
        </Button>
      </div>
    </form>
  );
}
