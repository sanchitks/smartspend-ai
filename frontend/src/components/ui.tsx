import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleMinus,
  Loader2,
  OctagonAlert,
  X,
} from "lucide-react";
import {
  useEffect,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

import { monthLabel } from "../lib/format";
import type { BudgetStatus } from "../lib/types";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

// ---------------------------------------------------------------- buttons

type Variant = "primary" | "secondary" | "ghost" | "danger";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-brand-hover border-transparent",
  secondary: "bg-surface text-ink border-line-strong hover:bg-canvas",
  ghost: "bg-transparent text-ink-2 border-transparent hover:bg-canvas",
  danger: "bg-surface text-critical-ink border-line-strong hover:bg-critical-soft",
};

export function Button({
  variant = "primary",
  size = "md",
  loading,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; loading?: boolean }) {
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        size === "sm" ? "h-8 px-3 text-sm" : "h-10 px-4 text-sm",
        VARIANTS[variant],
        className,
      )}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

// ---------------------------------------------------------------- layout

export function Card({ className, children, as: As = "section" }: { className?: string; children: ReactNode; as?: "section" | "div" | "article" }) {
  return <As className={cx("rounded-xl border border-line bg-surface", className)}>{children}</As>;
}

export function CardHeader({ title, action, subtitle }: { title: ReactNode; action?: ReactNode; subtitle?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 px-5 pt-4 pb-3">
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- forms

export function Field({ label, error, hint, children, htmlFor }: { label: string; error?: string; hint?: ReactNode; children: ReactNode; htmlFor: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium text-ink-2">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${htmlFor}-error`} className="flex items-center gap-1 text-sm text-critical-ink">
          <CircleAlert className="size-3.5 shrink-0" aria-hidden />
          {error}
        </p>
      ) : (
        hint && <p className="text-xs text-muted">{hint}</p>
      )}
    </div>
  );
}

const control =
  "h-10 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink placeholder:text-muted/80 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20 aria-[invalid=true]:border-critical";

export function Input({ className, invalid, ...rest }: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return (
    <input
      className={cx(control, className)}
      aria-invalid={invalid || undefined}
      aria-describedby={invalid && rest.id ? `${rest.id}-error` : undefined}
      {...rest}
    />
  );
}

export function Select({ className, invalid, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }) {
  return (
    <select className={cx(control, "pr-8", className)} aria-invalid={invalid || undefined} {...rest}>
      {children}
    </select>
  );
}

export function MoneyInput({ currencySymbol, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & { currencySymbol: string; invalid?: boolean }) {
  const { invalid, ...props } = rest as typeof rest & { invalid?: boolean };
  return (
    <div className="relative">
      <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-muted">{currencySymbol}</span>
      <input
        inputMode="decimal"
        autoComplete="off"
        className={cx(control, "tnum pl-8", className)}
        aria-invalid={invalid || undefined}
        {...props}
      />
    </div>
  );
}

export function symbolFor(currency: string) {
  return (
    { INR: "₹", USD: "$", EUR: "€", GBP: "£", AED: "AED", SGD: "S$", AUD: "A$", CAD: "C$" }[currency] ?? currency
  );
}

// ---------------------------------------------------------------- feedback

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-10 text-sm text-muted">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}…
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-md bg-line/70", className)} aria-hidden />;
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-10 text-center">
      {icon && <div className="mb-3 grid size-11 place-items-center rounded-full bg-brand-soft text-brand">{icon}</div>}
      <h3 className="font-semibold text-ink">{title}</h3>
      {children && <p className="mt-1 max-w-sm text-sm text-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 px-6 py-10 text-center">
      <AlertTriangle className="size-6 text-critical" aria-hidden />
      <p className="text-sm text-ink-2">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warning" | "error" | "success"; children: ReactNode }) {
  const styles = {
    info: "bg-brand-soft text-ink-2 border-brand/15",
    warning: "bg-warning-soft text-warning-ink border-warning/30",
    error: "bg-critical-soft text-critical-ink border-critical/20",
    success: "bg-good-soft text-good-ink border-good/25",
  }[tone];
  const Icon = { info: CircleAlert, warning: AlertTriangle, error: OctagonAlert, success: CheckCircle2 }[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cx("flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm", styles)}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------- budget status: colour + icon + word

export const STATUS: Record<BudgetStatus, { label: string; bar: string; badge: string; Icon: typeof CheckCircle2 }> = {
  healthy: { label: "On track", bar: "bg-good", badge: "bg-good-soft text-good-ink", Icon: CheckCircle2 },
  approaching: { label: "Approaching limit", bar: "bg-warning", badge: "bg-warning-soft text-warning-ink", Icon: CircleAlert },
  near_limit: { label: "Near limit", bar: "bg-serious", badge: "bg-serious-soft text-serious-ink", Icon: AlertTriangle },
  exceeded: { label: "Over budget", bar: "bg-critical", badge: "bg-critical-soft text-critical-ink", Icon: OctagonAlert },
  no_budget: { label: "No budget set", bar: "bg-line-strong", badge: "bg-canvas text-muted", Icon: CircleMinus },
};

export function StatusBadge({ status }: { status: BudgetStatus }) {
  const s = STATUS[status];
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap", s.badge)}>
      <s.Icon className="size-3.5" aria-hidden />
      {s.label}
    </span>
  );
}

export function ProgressBar({ value, status, label }: { value: number | null; status: BudgetStatus; label: string }) {
  const width = Math.max(0, Math.min(100, value ?? 0));
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-canvas ring-1 ring-line ring-inset"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(width)}
      aria-valuetext={value === null ? "No budget" : `${value}% used`}
    >
      <div className={cx("h-full rounded-full", STATUS[status].bar)} style={{ width: `${width}%` }} />
    </div>
  );
}

// ---------------------------------------------------------------- month picker

export function MonthPicker({ year, month, onChange, max }: { year: number; month: number; onChange: (y: number, m: number) => void; max?: { year: number; month: number } }) {
  const shift = (delta: number) => {
    const i = year * 12 + (month - 1) + delta;
    onChange(Math.floor(i / 12), (i % 12) + 1);
  };
  const atMax = max ? year * 12 + month >= max.year * 12 + max.month : false;
  return (
    <div className="inline-flex items-center rounded-lg border border-line-strong bg-surface">
      <button className="grid size-9 place-items-center rounded-l-lg text-ink-2 hover:bg-canvas" onClick={() => shift(-1)} aria-label="Previous month">
        <ChevronLeft className="size-4" aria-hidden />
      </button>
      <span className="min-w-36 px-2 text-center text-sm font-medium" aria-live="polite">
        {monthLabel(year, month)}
      </span>
      <button
        className="grid size-9 place-items-center rounded-r-lg text-ink-2 hover:bg-canvas disabled:opacity-40"
        onClick={() => shift(1)}
        disabled={atMax}
        aria-label="Next month"
      >
        <ChevronRight className="size-4" aria-hidden />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------- dialog

export function Dialog({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      className={cx(
        "m-auto w-[calc(100%-2rem)] rounded-2xl border border-line bg-surface p-0 text-ink shadow-xl backdrop:bg-ink/40",
        wide ? "max-w-2xl" : "max-w-lg",
      )}
    >
      {open && (
        <div className="max-h-[85vh] overflow-y-auto">
          <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-surface px-5 py-4">
            <h2 id={titleId} className="text-base font-semibold">
              {title}
            </h2>
            <button onClick={onClose} className="grid size-8 place-items-center rounded-lg text-muted hover:bg-canvas" aria-label="Close">
              <X className="size-4" aria-hidden />
            </button>
          </div>
          <div className="px-5 py-5">{children}</div>
        </div>
      )}
    </dialog>
  );
}

export function VisuallyHidden({ children }: { children: ReactNode }) {
  return <span className="sr-only">{children}</span>;
}
