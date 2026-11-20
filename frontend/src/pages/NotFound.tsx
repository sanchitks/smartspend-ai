import { Link } from "react-router";

import { Logo } from "../components/Logo";

export function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-canvas px-4 text-center">
      <Logo />
      <h1 className="mt-6 text-2xl font-semibold">Page not found</h1>
      <p className="text-sm text-muted">The page you were looking for doesn't exist.</p>
      <Link to="/app" className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover">
        Go to the dashboard
      </Link>
    </main>
  );
}
