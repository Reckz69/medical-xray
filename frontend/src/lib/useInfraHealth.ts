"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  checkInfra,
  checkReady,
  getToken,
  type InfraHealth,
  type ReadyResponse,
} from "@/lib/api";

export type InfraMode = "infra" | "ready" | "offline";

export interface InfraState {
  health: InfraHealth | null;
  ready: ReadyResponse | null;
  mode: InfraMode;
  error: string | null;
  lastUpdated: Date | null;
  refresh: () => Promise<void>;
}

/**
 * Polls `/health/infra` with the bearer token. When signed out in production
 * (401), falls back to the public `/health/ready` probe so the dashboard and
 * status page still render. Never throws.
 */
export function useInfraHealth(intervalMs = 15_000): InfraState {
  const [health, setHealth] = useState<InfraHealth | null>(null);
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [mode, setMode] = useState<InfraMode>("offline");
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const result = await checkInfra(getToken());
      if (!mounted.current) return;
      setHealth(result);
      setReady(null);
      setMode("infra");
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        const readyResult = await checkReady();
        if (!mounted.current) return;
        setHealth(null);
        setReady(readyResult);
        setMode("ready");
        setError(readyResult ? null : "Health check unavailable");
      } else {
        if (!mounted.current) return;
        setHealth(null);
        setReady(null);
        setMode("offline");
        setError(err instanceof Error ? err.message : "Health check failed");
      }
    }
    if (mounted.current) setLastUpdated(new Date());
  }, []);

  useEffect(() => {
    mounted.current = true;
    const initial = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(() => void refresh(), intervalMs);
    return () => {
      mounted.current = false;
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [refresh, intervalMs]);

  return { health, ready, mode, error, lastUpdated, refresh };
}
