import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, getToken, setToken } from "./api";
import type { User } from "./types";

interface TokenResponse {
  access_token: string;
  expires_at: string;
  user: User;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (name: string, email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  setUser: (u: User | null) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(() => Boolean(getToken()));

  useEffect(() => {
    if (!getToken()) return;
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const onSignedOut = () => setUser(null);
    window.addEventListener("smartspend:signed-out", onSignedOut);
    return () => window.removeEventListener("smartspend:signed-out", onSignedOut);
  }, []);

  const accept = useCallback((r: TokenResponse) => {
    setToken(r.access_token, r.expires_at);
    setUser(r.user);
    return r.user;
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      setUser,
      login: async (email, password) => accept(await api<TokenResponse>("/auth/login", { body: { email, password } })),
      register: async (name, email, password) =>
        accept(await api<TokenResponse>("/auth/register", { body: { name, email, password } })),
      logout: async () => {
        try {
          await api("/auth/logout", { method: "POST" });
        } catch {
          /* already signed out */
        }
        setToken(null);
        setUser(null);
      },
    }),
    [user, loading, accept],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
