"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, tokens } from "@/lib/api";
import type { User } from "@/lib/types";

interface AuthState {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => Promise<void>;
  setUser: (user: User) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUserState] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // Hydrate from localStorage for an instant first paint, then confirm the
    // session against the API so a revoked token doesn't linger in the UI.
    const cached = tokens.user();
    if (cached) setUserState(cached);

    if (!tokens.access()) {
      setReady(true);
      return;
    }

    let cancelled = false;
    api.auth
      .me()
      .then((fresh) => {
        if (cancelled) return;
        setUserState(fresh);
        tokens.saveUser(fresh);
      })
      .catch(() => {
        if (cancelled) return;
        tokens.clear();
        setUserState(null);
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const pair = await api.auth.login(email, password);
      tokens.save(pair);
      setUserState(pair.user);
    },
    [],
  );

  const register = useCallback(
    async (email: string, password: string, fullName?: string) => {
      const pair = await api.auth.register(email, password, fullName);
      tokens.save(pair);
      setUserState(pair.user);
    },
    [],
  );

  const logout = useCallback(async () => {
    await api.auth.logout();
    setUserState(null);
    router.push("/login");
  }, [router]);

  const setUser = useCallback((next: User) => {
    setUserState(next);
    tokens.saveUser(next);
  }, []);

  const value = useMemo(
    () => ({ user, ready, login, register, logout, setUser }),
    [user, ready, login, register, logout, setUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
