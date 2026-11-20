import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { Logo } from "../components/Logo";
import { Button, Field, MoneyInput, Notice, Select, symbolFor } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { CURRENCIES } from "../lib/format";
import type { User } from "../lib/types";

const COMMON_ZONES = ["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "Europe/Berlin", "America/New_York", "America/Los_Angeles", "Australia/Sydney"];

function timezones(): string[] {
  try {
    return (Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf("timeZone");
  } catch {
    return COMMON_ZONES;
  }
}

const isAmount = (s: string) => /^\d+(\.\d{1,2})?$/.test(s.replace(/,/g, ""));

export function Onboarding() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const zones = useMemo(() => {
    const all = timezones();
    return all.includes(browserZone) ? all : [browserZone, ...all];
  }, [browserZone]);
  const [currency, setCurrency] = useState(user?.currency ?? "INR");
  const [timezone, setTimezone] = useState(zones.includes(browserZone) ? browserZone : "Asia/Kolkata");
  const [income, setIncome] = useState("");
  const [budget, setBudget] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const found: Record<string, string> = {};
    if (income && !isAmount(income)) found.income = "Use a number like 50000.";
    if (budget && (!isAmount(budget) || Number(budget) <= 0)) found.budget = "Use a number greater than zero.";
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api<User>("/users/me", {
        method: "PATCH",
        body: { currency, timezone, monthly_income: income ? income.replace(/,/g, "") : null, onboarded: true },
      });
      if (budget) {
        const now = new Date();
        await api("/budgets", {
          body: { category_id: null, amount: budget.replace(/,/g, ""), year: now.getFullYear(), month: now.getMonth() + 1 },
        }).catch(() => undefined); // a budget may already exist; it can be set later
      }
      setUser(updated);
      navigate("/app", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save your settings. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-dvh flex-col items-center bg-canvas px-4 py-10">
      <Logo className="mb-8" />
      <main className="w-full max-w-lg rounded-2xl border border-line bg-surface p-6 sm:p-8">
        <p className="text-sm font-medium text-brand">Step 1 of 1</p>
        <h1 className="mt-1 text-xl font-semibold tracking-tight">Set up your account, {user?.name.split(" ")[0]}</h1>
        <p className="mt-1 text-sm text-muted">Budgets run on calendar months. You can change these later in Settings.</p>
        <form onSubmit={submit} noValidate className="mt-6 flex flex-col gap-4">
          {error && <Notice tone="error">{error}</Notice>}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Currency" htmlFor="currency" hint="Used for every amount.">
              <Select id="currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                {CURRENCIES.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </Select>
            </Field>
            <Field label="Timezone" htmlFor="tz" hint="Decides what “today” means.">
              <Select id="tz" value={timezone} onChange={(e) => setTimezone(e.target.value)}>
                {zones.map((z) => (
                  <option key={z}>{z}</option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Approximate monthly income (optional)" htmlFor="income" error={errors.income}>
            <MoneyInput id="income" currencySymbol={symbolFor(currency)} value={income} onChange={(e) => setIncome(e.target.value)} placeholder="50000" invalid={Boolean(errors.income)} />
          </Field>
          <Field label="Total budget for this month (optional)" htmlFor="budget" error={errors.budget} hint="The most you want to spend this month across everything.">
            <MoneyInput id="budget" currencySymbol={symbolFor(currency)} value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="30000" invalid={Boolean(errors.budget)} />
          </Field>
          <div className="mt-2 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button type="submit" loading={busy}>
              Go to my dashboard
            </Button>
          </div>
        </form>
      </main>
    </div>
  );
}
