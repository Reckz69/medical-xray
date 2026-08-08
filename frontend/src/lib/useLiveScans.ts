"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { listScans, type Scan } from "@/lib/api";
import { getSettings } from "@/lib/settings";

export interface LiveScansState {
  scans: Scan[];
  total: number;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  refresh: () => Promise<void>;
}

/**
 * Polls `GET /scans` on an interval (default from the user's settings) and
 * returns the freshest list. Used by the dashboard and gallery so live status
 * transitions (QUEUED -> RUNNING -> COMPLETED) surface without manual refresh.
 */
export function useLiveScans(limit = 50, intervalMs?: number): LiveScansState {
  const [scans, setScans] = useState<Scan[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const result = await listScans(0, limit);
      if (!mounted.current) return;
      setScans(result.items);
      setTotal(result.total);
      setError(null);
      setLastUpdated(new Date());
    } catch (err) {
      if (!mounted.current) return;
      setError(err instanceof Error ? err.message : "Failed to load scans");
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    mounted.current = true;
    const initial = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(
      () => void refresh(),
      intervalMs ?? getSettings().pollIntervalSeconds * 1000
    );
    return () => {
      mounted.current = false;
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [refresh, intervalMs]);

  return { scans, total, loading, error, lastUpdated, refresh };
}
