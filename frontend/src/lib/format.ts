// Consistent display formatting for money, dates and percentages.
const formatters = new Map<string, Intl.NumberFormat>();

function moneyFormat(currency: string, compact: boolean) {
  const key = `${currency}:${compact}`;
  let f = formatters.get(key);
  if (!f) {
    f = new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en", {
      style: "currency",
      currency,
      minimumFractionDigits: compact ? 0 : 2,
      maximumFractionDigits: compact ? 1 : 2,
      notation: compact ? "compact" : "standard",
    });
    formatters.set(key, f);
  }
  return f;
}

/** ₹1,23,456.50 — trailing ".00" dropped for whole amounts. Negative amounts show a minus sign. */
export function money(value: string | number | null | undefined, currency = "INR"): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  const text = moneyFormat(currency, false).format(n);
  return Number.isInteger(n) ? text.replace(/\.00(?=\D*$)/, "") : text;
}

export function moneyCompact(value: string | number, currency = "INR"): string {
  return moneyFormat(currency, true).format(Number(value));
}

export function signedMoney(value: string | number, type: "income" | "expense", currency = "INR"): string {
  return (type === "income" ? "+" : "−") + money(value, currency);
}

export function pct(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  return `${Number.isInteger(n) ? n : n.toFixed(1)}%`;
}

const dayFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
const shortFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" });
const monthFmt = new Intl.DateTimeFormat("en-IN", { month: "long", year: "numeric" });

function parseDate(iso: string) {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export const date = (iso: string) => dayFmt.format(parseDate(iso));
export const shortDate = (iso: string) => shortFmt.format(parseDate(iso));
export const monthLabel = (year: number, month: number) => monthFmt.format(new Date(year, month - 1, 1));

export function isoToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function relativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  if (diff < 7 * 86400) return `${Math.floor(diff / 86400)} d ago`;
  return date(iso);
}

export const PAYMENT_METHODS: Record<string, string> = {
  cash: "Cash",
  upi: "UPI",
  debit_card: "Debit card",
  credit_card: "Credit card",
  net_banking: "Net banking",
  wallet: "Wallet",
  other: "Other",
};

export const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SGD", "AUD", "CAD"];
