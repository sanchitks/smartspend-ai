import { ArrowRight, CalendarRange, Calculator, ShieldCheck } from "lucide-react";
import { Link } from "react-router";

import { Logo } from "../components/Logo";
import { useAuth } from "../lib/auth";

export function Landing() {
  const { user } = useAuth();
  return (
    <div className="min-h-dvh bg-surface">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <Logo />
        <nav className="flex items-center gap-2 text-sm">
          {user ? (
            <Link to="/app" className="rounded-lg bg-brand px-4 py-2 font-medium text-white hover:bg-brand-hover">
              Open dashboard
            </Link>
          ) : (
            <>
              <Link to="/login" className="rounded-lg px-3 py-2 font-medium text-ink-2 hover:bg-canvas">
                Log in
              </Link>
              <Link to="/register" className="rounded-lg bg-brand px-4 py-2 font-medium text-white hover:bg-brand-hover">
                Create account
              </Link>
            </>
          )}
        </nav>
      </header>

      <main className="mx-auto grid max-w-6xl items-center gap-12 px-4 pt-10 pb-20 sm:px-6 lg:grid-cols-[1.1fr_1fr] lg:pt-16">
        <section>
          <p className="text-sm font-medium text-brand">Personal budgeting, without the spreadsheet</p>
          <h1 className="mt-3 text-4xl leading-[1.1] font-semibold tracking-tight text-ink sm:text-5xl">
            Understand your money. Control your spending. Build better habits.
          </h1>
          <p className="mt-5 max-w-xl text-lg text-ink-2">
            Write “spent ₹450 on dinner” and SmartSpend fills in the details for you to check. Set monthly limits, see
            where your money goes, and ask questions about your own spending in plain language.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              to={user ? "/app" : "/register"}
              className="inline-flex items-center gap-2 rounded-lg bg-brand px-5 py-3 font-medium text-white hover:bg-brand-hover"
            >
              {user ? "Go to your dashboard" : "Start for free"} <ArrowRight className="size-4" aria-hidden />
            </Link>
          </div>
          <ul className="mt-10 grid gap-4 text-sm text-ink-2 sm:grid-cols-3">
            <li className="flex gap-2">
              <Calculator className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden />
              Totals are calculated from your records, never guessed by AI.
            </li>
            <li className="flex gap-2">
              <CalendarRange className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden />
              Alerts at 75%, 90% and over 100% of each budget.
            </li>
            <li className="flex gap-2">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden />
              Your records stay private to your account.
            </li>
          </ul>
        </section>

        {/* A static example of an assistant answer, to show what "grounded" means. */}
        <section aria-label="Example" className="rounded-2xl border border-line bg-canvas p-4 sm:p-6">
          <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-sm text-white">
            How much did I spend on transport this month?
          </div>
          <div className="mt-4 rounded-2xl rounded-bl-md border border-line bg-surface p-4 text-sm">
            <p className="text-ink">
              You spent <strong className="font-semibold">₹2,340</strong> on Transportation in November 2026 so far
              (1–20 Nov), across 14 transactions.
            </p>
            <dl className="tnum mt-3 grid grid-cols-2 gap-2 border-t border-line pt-3 text-xs">
              <div>
                <dt className="text-muted">Spent on Transportation</dt>
                <dd className="font-medium text-ink">₹2,340</dd>
              </div>
              <div>
                <dt className="text-muted">Transactions</dt>
                <dd className="font-medium text-ink">14</dd>
              </div>
            </dl>
            <p className="mt-3 text-xs text-muted">Calculated from your records · 1–20 Nov 2026</p>
          </div>
          <p className="mt-4 text-center text-xs text-muted">Example answer</p>
        </section>
      </main>

      <footer className="border-t border-line">
        <p className="mx-auto max-w-6xl px-4 py-6 text-xs text-muted sm:px-6">
          SmartSpend AI provides general budgeting assistance, not regulated financial advice. It doesn't connect to
          your bank or move money.
        </p>
      </footer>
    </div>
  );
}
