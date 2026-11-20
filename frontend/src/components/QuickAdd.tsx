import { ArrowRight, Sparkles } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { ApiError, api } from "../lib/api";
import type { ParseResult, TxnType } from "../lib/types";
import { TransactionForm, emptyValues, type TxnValues } from "./TransactionForm";
import { Button, Dialog, Input, Notice } from "./ui";

export function draftToValues(r: ParseResult): TxnValues {
  const d = r.draft;
  const type: TxnType = d.transaction_type === "income" ? "income" : "expense";
  return {
    ...emptyValues(type),
    amount: d.amount ?? "",
    category_id: d.category_id ? String(d.category_id) : "",
    description: d.description ?? "",
    transaction_date: d.transaction_date ?? emptyValues().transaction_date,
    payment_method: d.payment_method ?? "",
  };
}

const FIELD_NAMES: Record<string, string> = {
  amount: "amount",
  transaction_type: "type",
  category: "category",
  transaction_date: "date",
};

/** Draft review: nothing is saved until the person presses "Save transaction". */
export function DraftReview({ result, onDone, onCancel }: { result: ParseResult; onDone: () => void; onCancel: () => void }) {
  const missing = result.missing_fields.map((f) => FIELD_NAMES[f] ?? f);
  return (
    <div className="flex flex-col gap-4">
      <Notice tone="info">
        <strong className="font-medium">Check before saving.</strong> This was filled in from your description
        {result.provider === "demo" ? " by the offline demo assistant" : ""}. Edit anything that's wrong.
        {missing.length > 0 && <> Still needed: {missing.join(", ")}.</>}
      </Notice>
      <TransactionForm
        initial={draftToValues(result)}
        source="ai"
        highlight={result.missing_fields.map((f) => (f === "category" ? "category_id" : f))}
        onSaved={onDone}
        onCancel={onCancel}
        submitLabel="Save transaction"
      />
    </div>
  );
}

export function QuickAdd({ onManual }: { onManual: () => void }) {
  const id = useId();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ParseResult | null>(null);
  const [question, setQuestion] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    setQuestion(null);
    setSaved(false);
    try {
      const r = await api<ParseResult>("/ai/transactions/parse", {
        body: { text, locale: navigator.language || "en-IN", timezone: Intl.DateTimeFormat().resolvedOptions().timeZone },
      });
      if (r.needs_clarification && !r.draft.amount) setQuestion(r.clarification_question);
      else setResult(r);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't read that. Try again or add it manually.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <label htmlFor={`${id}-q`} className="sr-only">
          Describe a transaction
        </label>
        <div className="relative flex-1">
          <Sparkles className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-brand" aria-hidden />
          <Input
            id={`${id}-q`}
            value={text}
            maxLength={300}
            onChange={(e) => setText(e.target.value)}
            placeholder="Describe it: “Spent ₹450 on dinner today”"
            className="pl-9"
          />
        </div>
        <Button type="submit" loading={busy} disabled={!text.trim()}>
          Fill in for me <ArrowRight className="size-4" aria-hidden />
        </Button>
      </form>
      <div className="mt-2 space-y-2" aria-live="polite">
        {question && (
          <Notice tone="warning">
            {question} Add it to your description and try again.
          </Notice>
        )}
        {error && (
          <Notice tone="error">
            {error}{" "}
            <button className="font-medium underline" onClick={onManual}>
              Add manually
            </button>
          </Notice>
        )}
        {saved && <Notice tone="success">Saved. Your dashboard and budgets are up to date.</Notice>}
      </div>
      <Dialog open={Boolean(result)} onClose={() => setResult(null)} title="Review transaction">
        {result && (
          <DraftReview
            result={result}
            onCancel={() => setResult(null)}
            onDone={() => {
              setResult(null);
              setText("");
              setSaved(true);
            }}
          />
        )}
      </Dialog>
    </div>
  );
}
