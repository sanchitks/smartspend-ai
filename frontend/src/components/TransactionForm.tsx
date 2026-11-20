import { useId, useMemo, useState, type FormEvent } from "react";

import { ApiError, api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { notifyDataChanged } from "../lib/events";
import { PAYMENT_METHODS, isoToday } from "../lib/format";
import type { Category, Transaction, TxnType } from "../lib/types";
import { useApi } from "../lib/useApi";
import { Button, Field, Input, MoneyInput, Notice, Select, cx, symbolFor } from "./ui";

export interface TxnValues {
  type: TxnType;
  amount: string;
  category_id: string;
  description: string;
  transaction_date: string;
  payment_method: string;
  notes: string;
}

export function emptyValues(type: TxnType = "expense"): TxnValues {
  return { type, amount: "", category_id: "", description: "", transaction_date: isoToday(), payment_method: "", notes: "" };
}

export function valuesFrom(t: Transaction): TxnValues {
  return {
    type: t.type,
    amount: t.amount,
    category_id: String(t.category.id),
    description: t.description,
    transaction_date: t.transaction_date,
    payment_method: t.payment_method ?? "",
    notes: t.notes ?? "",
  };
}

function validate(v: TxnValues): Record<string, string> {
  const e: Record<string, string> = {};
  const amount = v.amount.replace(/,/g, "").trim();
  if (!amount) e.amount = "Enter an amount.";
  else if (!/^\d+(\.\d{1,2})?$/.test(amount)) e.amount = "Use a number with up to 2 decimal places.";
  else if (Number(amount) <= 0) e.amount = "Amount must be greater than zero.";
  if (!v.category_id) e.category_id = "Choose a category.";
  if (!v.description.trim()) e.description = "Add a short description.";
  if (!v.transaction_date) e.transaction_date = "Choose a date.";
  return e;
}

export function TransactionForm({
  initial,
  transactionId,
  source = "manual",
  highlight = [],
  onSaved,
  onCancel,
  submitLabel,
}: {
  initial: TxnValues;
  transactionId?: number;
  source?: "manual" | "ai";
  highlight?: string[];
  onSaved: (t: Transaction) => void;
  onCancel: () => void;
  submitLabel?: string;
}) {
  const { user } = useAuth();
  const id = useId();
  const [v, setV] = useState<TxnValues>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const { data: categories } = useApi<Category[]>("/categories");
  const options = useMemo(() => (categories ?? []).filter((c) => c.type === v.type), [categories, v.type]);
  const set = <K extends keyof TxnValues>(k: K, value: TxnValues[K]) => setV((prev) => ({ ...prev, [k]: value }));
  const isFuture = v.transaction_date > isoToday();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const found = validate(v);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length) return;
    setSaving(true);
    const body = {
      type: v.type,
      amount: v.amount.replace(/,/g, "").trim(),
      category_id: Number(v.category_id),
      description: v.description.trim(),
      transaction_date: v.transaction_date,
      payment_method: v.payment_method || null,
      notes: v.notes.trim() || null,
      ...(transactionId ? {} : { source }),
    };
    try {
      const saved = transactionId
        ? await api<Transaction>(`/transactions/${transactionId}`, { method: "PATCH", body })
        : await api<Transaction>("/transactions", { body });
      notifyDataChanged();
      onSaved(saved);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors());
        setFormError(err.message);
      } else setFormError("Something went wrong. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  const mark = (field: string) => highlight.includes(field) && !v[field as keyof TxnValues];

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      {formError && Object.keys(errors).length === 0 && <Notice tone="error">{formError}</Notice>}

      <fieldset>
        <legend className="mb-1.5 text-sm font-medium text-ink-2">Type</legend>
        <div className="grid grid-cols-2 gap-1 rounded-lg bg-canvas p-1">
          {(["expense", "income"] as const).map((t) => (
            <label
              key={t}
              className={cx(
                "flex cursor-pointer items-center justify-center rounded-md py-1.5 text-sm font-medium has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand",
                v.type === t ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink",
              )}
            >
              <input
                type="radio"
                name={`${id}-type`}
                value={t}
                checked={v.type === t}
                onChange={() => setV((p) => ({ ...p, type: t, category_id: "" }))}
                className="sr-only"
              />
              {t === "expense" ? "Expense" : "Income"}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Amount" htmlFor={`${id}-amount`} error={errors.amount}>
          <MoneyInput
            id={`${id}-amount`}
            currencySymbol={symbolFor(user?.currency ?? "INR")}
            value={v.amount}
            onChange={(e) => set("amount", e.target.value)}
            placeholder="0.00"
            invalid={Boolean(errors.amount) || mark("amount")}
            autoFocus={!transactionId}
          />
        </Field>
        <Field label="Date" htmlFor={`${id}-date`} error={errors.transaction_date} hint={isFuture ? "This date is in the future." : undefined}>
          <Input id={`${id}-date`} type="date" value={v.transaction_date} onChange={(e) => set("transaction_date", e.target.value)} invalid={Boolean(errors.transaction_date)} />
        </Field>
      </div>

      <Field label="Category" htmlFor={`${id}-category`} error={errors.category_id}>
        <Select
          id={`${id}-category`}
          value={v.category_id}
          onChange={(e) => set("category_id", e.target.value)}
          invalid={Boolean(errors.category_id) || mark("category_id")}
        >
          <option value="">Choose a category</option>
          {options.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </Select>
      </Field>

      <Field label="Description" htmlFor={`${id}-desc`} error={errors.description}>
        <Input
          id={`${id}-desc`}
          value={v.description}
          maxLength={200}
          onChange={(e) => set("description", e.target.value)}
          placeholder={v.type === "expense" ? "e.g. Dinner with friends" : "e.g. November salary"}
          invalid={Boolean(errors.description)}
        />
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Payment method (optional)" htmlFor={`${id}-pm`}>
          <Select id={`${id}-pm`} value={v.payment_method} onChange={(e) => set("payment_method", e.target.value)}>
            <option value="">Not specified</option>
            {Object.entries(PAYMENT_METHODS).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Notes (optional)" htmlFor={`${id}-notes`}>
          <Input id={`${id}-notes`} value={v.notes} maxLength={1000} onChange={(e) => set("notes", e.target.value)} />
        </Field>
      </div>

      <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" loading={saving}>
          {submitLabel ?? (transactionId ? "Save changes" : "Add transaction")}
        </Button>
      </div>
    </form>
  );
}
