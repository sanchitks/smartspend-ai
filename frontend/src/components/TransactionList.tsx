import { Sparkles } from "lucide-react";

import { useAuth } from "../lib/auth";
import { PAYMENT_METHODS, date, shortDate, signedMoney } from "../lib/format";
import type { Transaction } from "../lib/types";
import { cx } from "./ui";

/** Compact list used on the dashboard; the Transactions page has the full table. */
export function TransactionList({ items, onSelect }: { items: Transaction[]; onSelect?: (t: Transaction) => void }) {
  const { user } = useAuth();
  return (
    <ul className="divide-y divide-line">
      {items.map((t) => (
        <li key={t.id}>
          <button
            className="flex w-full items-center gap-3 px-5 py-3 text-left hover:bg-canvas disabled:hover:bg-transparent"
            onClick={() => onSelect?.(t)}
            disabled={!onSelect}
          >
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-1.5 truncate text-sm font-medium text-ink">
                {t.description}
                {t.source === "ai" && <Sparkles className="size-3.5 shrink-0 text-brand" aria-label="Added with AI help" />}
              </p>
              <p className="truncate text-xs text-muted">
                {t.category.name} · <time dateTime={t.transaction_date} title={date(t.transaction_date)}>{shortDate(t.transaction_date)}</time>
                {t.payment_method && ` · ${PAYMENT_METHODS[t.payment_method] ?? t.payment_method}`}
                {t.is_future && " · upcoming"}
              </p>
            </div>
            <span className={cx("tnum text-sm font-medium whitespace-nowrap", t.type === "income" ? "text-good-ink" : "text-ink")}>
              {signedMoney(t.amount, t.type, user?.currency)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
