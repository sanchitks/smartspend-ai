import "./index.css";

import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { Navigate, RouterProvider, createBrowserRouter, useLocation } from "react-router";

import { AppShell } from "./components/AppShell";
import { Spinner } from "./components/ui";
import { AuthProvider, useAuth } from "./lib/auth";
import { Analytics } from "./pages/Analytics";
import { Assistant } from "./pages/Assistant";
import { Login, Register } from "./pages/Auth";
import { Budgets } from "./pages/Budgets";
import { Dashboard } from "./pages/Dashboard";
import { Goals } from "./pages/Goals";
import { Landing } from "./pages/Landing";
import { NotFound } from "./pages/NotFound";
import { Notifications } from "./pages/Notifications";
import { Onboarding } from "./pages/Onboarding";
import { Settings } from "./pages/Settings";
import { Transactions } from "./pages/Transactions";

function RequireAuth({ children, allowNotOnboarded }: { children: ReactNode; allowNotOnboarded?: boolean }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner label="Loading your account" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (!user.onboarded && !allowNotOnboarded) return <Navigate to="/onboarding" replace />;
  return <>{children}</>;
}

const router = createBrowserRouter([
  { path: "/", element: <Landing /> },
  { path: "/login", element: <Login /> },
  { path: "/register", element: <Register /> },
  {
    path: "/onboarding",
    element: (
      <RequireAuth allowNotOnboarded>
        <Onboarding />
      </RequireAuth>
    ),
  },
  {
    path: "/app",
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Dashboard /> },
      { path: "transactions", element: <Transactions /> },
      { path: "budgets", element: <Budgets /> },
      { path: "analytics", element: <Analytics /> },
      { path: "assistant", element: <Assistant /> },
      { path: "goals", element: <Goals /> },
      { path: "notifications", element: <Notifications /> },
      { path: "settings", element: <Settings /> },
    ],
  },
  { path: "*", element: <NotFound /> },
], { basename: import.meta.env.BASE_URL.replace(/\/$/, "") || "/" });

// Refuse to run inside another site's frame (clickjacking); GitHub Pages can't send X-Frame-Options.
if (window.top !== window.self) {
  document.documentElement.style.display = "none";
  try {
    window.top!.location.href = window.location.href;
  } catch {
    /* stays hidden */
  }
  throw new Error("SmartSpend can't be shown inside a frame.");
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  </StrictMode>,
);
