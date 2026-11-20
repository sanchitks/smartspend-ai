import { Eye, EyeOff } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";

import { Logo } from "../components/Logo";
import { Button, Field, Input, Notice } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { useAuth } from "../lib/auth";

/** The free API host sleeps when idle; tell people why the first request is slow instead of looking broken. */
function useServerWaking() {
  const [waking, setWaking] = useState(false);
  useEffect(() => {
    let done = false;
    const timer = setTimeout(() => !done && setWaking(true), 2500);
    api("/health")
      .catch(() => undefined)
      .finally(() => {
        done = true;
        clearTimeout(timer);
        setWaking(false);
      });
    return () => clearTimeout(timer);
  }, []);
  return waking;
}

function AuthLayout({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  const waking = useServerWaking();
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-canvas px-4 py-10">
      <Link to="/" aria-label="SmartSpend AI home" className="mb-8">
        <Logo />
      </Link>
      <main className="w-full max-w-sm rounded-2xl border border-line bg-surface p-6 sm:p-8">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 text-sm text-muted">{subtitle}</p>
        {waking && (
          <div className="mt-4">
            <Notice tone="info">Starting up the server. This can take up to a minute after a quiet spell.</Notice>
          </div>
        )}
        <div className="mt-6">{children}</div>
      </main>
      <p className="mt-6 text-sm text-ink-2">{footer}</p>
    </div>
  );
}

function PasswordInput({ id, value, onChange, invalid, autoComplete }: { id: string; value: string; onChange: (v: string) => void; invalid?: boolean; autoComplete: string }) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input id={id} type={show ? "text" : "password"} value={value} onChange={(e) => onChange(e.target.value)} invalid={invalid} autoComplete={autoComplete} className="pr-10" />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        className="absolute inset-y-0 right-0 grid w-10 place-items-center text-muted hover:text-ink"
        aria-label={show ? "Hide password" : "Show password"}
      >
        {show ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
      </button>
    </div>
  );
}

export function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/app";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={from} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!email || !password) return setError("Enter your email and password.");
    setBusy(true);
    setError(null);
    try {
      const u = await login(email, password);
      navigate(u.onboarded ? from : "/onboarding", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't log in. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Log in"
      subtitle="Welcome back to SmartSpend AI."
      footer={
        <>
          New here?{" "}
          <Link to="/register" className="font-medium text-brand hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="Email" htmlFor="email">
          <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password" htmlFor="password">
          <PasswordInput id="password" value={password} onChange={setPassword} autoComplete="current-password" />
        </Field>
        <Button type="submit" loading={busy} className="mt-2 w-full">
          Log in
        </Button>
      </form>
    </AuthLayout>
  );
}

export function Register() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={user.onboarded ? "/app" : "/onboarding"} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    const found: Record<string, string> = {};
    if (!name.trim()) found.name = "Enter your name.";
    if (!/^\S+@\S+\.\S+$/.test(email)) found.email = "Enter a valid email address.";
    if (password.length < 8) found.password = "Use at least 8 characters.";
    setErrors(found);
    setError(null);
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      await register(name.trim(), email.trim(), password);
      navigate("/onboarding", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors());
        setError(err.message);
      } else setError("Couldn't create your account. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="It takes under a minute."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-brand hover:underline">
            Log in
          </Link>
        </>
      }
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        {error && !Object.keys(errors).length && <Notice tone="error">{error}</Notice>}
        <Field label="Name" htmlFor="name" error={errors.name}>
          <Input id="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} invalid={Boolean(errors.name)} maxLength={80} />
        </Field>
        <Field label="Email" htmlFor="email" error={errors.email}>
          <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} invalid={Boolean(errors.email)} />
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password} hint="At least 8 characters.">
          <PasswordInput id="password" value={password} onChange={setPassword} invalid={Boolean(errors.password)} autoComplete="new-password" />
        </Field>
        <Button type="submit" loading={busy} className="mt-2 w-full">
          Create account
        </Button>
        <p className="text-xs leading-relaxed text-muted">
          Your records are private to your account. When you use AI features, the text you type and relevant spending
          summaries are sent to an AI provider to produce an answer. SmartSpend gives general budgeting help, not
          financial advice.
        </p>
      </form>
    </AuthLayout>
  );
}
