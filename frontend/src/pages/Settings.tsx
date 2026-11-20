import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { Button, Card, CardHeader, Dialog, Field, Input, MoneyInput, Notice, PageHeader, Select, symbolFor } from "../components/ui";
import { ApiError, api, setToken } from "../lib/api";
import { useAuth } from "../lib/auth";
import { CURRENCIES } from "../lib/format";
import type { AIStatus, User } from "../lib/types";
import { useApi } from "../lib/useApi";

function zones(current: string): string[] {
  try {
    const all = (Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf("timeZone");
    return all.includes(current) ? all : [current, ...all];
  } catch {
    return [current];
  }
}

export function Settings() {
  const { user, setUser } = useAuth();
  const status = useApi<AIStatus>("/ai/status");
  const [name, setName] = useState(user?.name ?? "");
  const [currency, setCurrency] = useState(user?.currency ?? "INR");
  const [timezone, setTimezone] = useState(user?.timezone ?? "Asia/Kolkata");
  const [income, setIncome] = useState(user?.monthly_income ?? "");
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const tzList = useMemo(() => zones(user?.timezone ?? "Asia/Kolkata"), [user?.timezone]);

  async function save(e: FormEvent) {
    e.preventDefault();
    const cleanIncome = String(income).replace(/,/g, "").trim();
    if (cleanIncome && !/^\d+(\.\d{1,2})?$/.test(cleanIncome)) return setMsg({ tone: "error", text: "Monthly income should be a number like 50000." });
    setBusy(true);
    setMsg(null);
    try {
      const u = await api<User>("/users/me", { method: "PATCH", body: { name: name.trim(), currency, timezone, monthly_income: cleanIncome || null } });
      setUser(u);
      setMsg({ tone: "success", text: "Settings saved." });
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Couldn't save your settings." });
      setCurrency(user?.currency ?? "INR");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Profile & Settings" description={user?.email} />
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <Card>
          <CardHeader title="Preferences" />
          <form onSubmit={save} noValidate className="flex flex-col gap-4 px-5 pb-5">
            {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
            <Field label="Name" htmlFor="s-name">
              <Input id="s-name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Currency" htmlFor="s-currency" hint="Locked once you've added transactions, so totals are never mixed.">
                <Select id="s-currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                  {CURRENCIES.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Timezone" htmlFor="s-tz">
                <Select id="s-tz" value={timezone} onChange={(e) => setTimezone(e.target.value)}>
                  {tzList.map((z) => (
                    <option key={z}>{z}</option>
                  ))}
                </Select>
              </Field>
            </div>
            <Field label="Approximate monthly income (optional)" htmlFor="s-income">
              <MoneyInput id="s-income" currencySymbol={symbolFor(currency)} value={income} onChange={(e) => setIncome(e.target.value)} />
            </Field>
            <div className="flex justify-end">
              <Button type="submit" loading={busy}>
                Save settings
              </Button>
            </div>
          </form>
        </Card>

        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader title="AI and your data" />
            <div className="flex flex-col gap-3 px-5 pb-5 text-sm text-ink-2">
              <p>
                {status.data?.live
                  ? `AI features use Claude (${status.data.model}). Only the text you type and the summary figures needed for an answer are sent; never your password, email or full transaction history.`
                  : "AI features are running in demo mode on this server: nothing is sent to an outside AI provider."}
              </p>
              <p>All totals, budgets and comparisons are calculated by SmartSpend from your records. {status.data?.disclaimer}</p>
              <Button
                variant="secondary"
                size="sm"
                className="self-start"
                onClick={async () => {
                  if (!window.confirm("Delete all your assistant conversations?")) return;
                  await api("/ai/conversations", { method: "DELETE" }).catch(() => undefined);
                  setMsg({ tone: "success", text: "Chat history cleared." });
                }}
              >
                Clear chat history
              </Button>
            </div>
          </Card>
          <Card>
            <CardHeader title="Delete account" />
            <div className="px-5 pb-5 text-sm text-ink-2">
              <p>Permanently deletes your account, transactions, budgets, goals, alerts and chats. Export your transactions first if you want a copy.</p>
              <Button variant="danger" size="sm" className="mt-3" onClick={() => setDeleting(true)}>
                Delete my account
              </Button>
            </div>
          </Card>
        </div>
      </div>
      <DeleteAccount open={deleting} onClose={() => setDeleting(false)} />
    </>
  );
}

function DeleteAccount({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open={open} onClose={onClose} title="Delete your account?">
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            await api("/users/me", { method: "DELETE", body: { password } });
            setToken(null);
            setUser(null);
            navigate("/", { replace: true });
          } catch (err) {
            setError(err instanceof ApiError ? err.message : "Couldn't delete the account.");
          } finally {
            setBusy(false);
          }
        }}
      >
        {error && <Notice tone="error">{error}</Notice>}
        <p className="text-sm text-ink-2">This can't be undone. Enter your password to confirm.</p>
        <Field label="Password" htmlFor="del-pw">
          <Input id="del-pw" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="danger" loading={busy} disabled={!password}>
            Delete everything
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
