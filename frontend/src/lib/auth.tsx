"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import * as api from "@/lib/api";

interface AuthContextValue {
  user: api.User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<api.User>;
  signUp: (
    name: string,
    email: string,
    password: string,
    organizationName?: string
  ) => Promise<api.User>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<api.User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const restore = async () => {
      if (!api.hasToken()) {
        setLoading(false);
        return;
      }
      try {
        const current = await api.me();
        if (!cancelled) setUser(current);
      } catch {
        const refreshed = await api.refreshSession();
        if (refreshed) {
          try {
            const current = await api.me();
            if (!cancelled) setUser(current);
          } catch {
            if (!cancelled) setUser(null);
          }
        } else {
          if (!cancelled) setUser(null);
        }
      }
      if (!cancelled) setLoading(false);
    };

    void restore();

    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const current = await api.login(email, password);
    setUser(current);
    return current;
  }, []);

  const signUp = useCallback(
    async (
      name: string,
      email: string,
      password: string,
      organizationName?: string
    ) => {
      const current = await api.register({
        name,
        email,
        password,
        organization_name: organizationName,
      });
      setUser(current);
      return current;
    },
    []
  );

  const signOut = useCallback(async () => {
    await api.logout();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, signIn, signUp, signOut }),
    [user, loading, signIn, signUp, signOut]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
