"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Database,
  GitBranch,
  Loader2,
  RefreshCw,
  Server,
  Wifi,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { useInfraHealth } from "@/lib/useInfraHealth";

const CHECK_LABELS: Record<string, string> = {
  postgres: "PostgreSQL",
  redis: "Redis",
  rabbitmq: "RabbitMQ",
  storage: "Object Storage (MinIO)",
};

function Row({
  label,
  value,
  ok,
  mono,
}: {
  label: string;
  value: string;
  ok?: boolean;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5 rounded-xl bg-[oklch(0.97_0.01_285)]">
      <span className="text-sm font-medium text-[oklch(0.35_0.05_280)]">{label}</span>
      <span
        className={`inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full border ${
          ok == null
            ? "bg-gray-50 border-gray-200 text-gray-600"
            : ok
              ? "bg-emerald-50 border-emerald-200 text-emerald-700"
              : "bg-red-50 border-red-200 text-red-700"
        } ${mono ? "font-mono" : ""}`}
      >
        {ok != null &&
          (ok ? <CheckCircle2 className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />)}
        {value}
      </span>
    </div>
  );
}

function formatAge(iso: string | null, now: number): string {
  if (!iso) return "—";
  const ms = Math.max(0, now - new Date(iso).getTime());
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s ago`;
}

export default function StatusPage() {
  const { user, loading: authLoading } = useAuth();
  const { health, ready, mode, error, lastUpdated, refresh } = useInfraHealth(15_000);
  const [now, setNow] = useState<number>(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  if (authLoading) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-[oklch(0.98_0.005_285)] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-[oklch(0.52_0.22_155)] animate-spin" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-[oklch(0.98_0.005_285)] orb-bg flex items-center justify-center px-6">
        <div className="glass-card rounded-2xl p-10 max-w-md text-center shadow-sm border border-[oklch(0.91_0.015_285)]">
          <div className="w-12 h-12 rounded-2xl btn-purple flex items-center justify-center mx-auto mb-4">
            <Activity className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-2xl font-extrabold text-[oklch(0.14_0.02_275)] mb-2">
            Sign in to view system <span className="text-gradient">status</span>
          </h1>
          <p className="text-[oklch(0.55_0.04_280)] text-sm mb-6">
            The operational health matrix is only available to signed-in users.
          </p>
          <Link href="/signin" className="inline-block">
            <Button id="go-signin" className="btn-purple rounded-xl px-8 h-11 font-bold">
              Sign In / Create Account
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  const status = health?.status ?? ready?.status ?? "unknown";
  const ok = status === "ok";
  const checkedAt = health?.checked_at ?? lastUpdated?.toISOString() ?? null;
  const checks = health?.checks ?? ready?.checks ?? null;

  return (
    <div className="min-h-screen bg-[oklch(0.98_0.005_285)] orb-bg pb-20">
      <div className="max-w-4xl mx-auto px-6 md:px-12 py-12 flex flex-col gap-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-3">
              <div className="pill-badge">
                <Activity className="w-3 h-3" />
                Operational Health
              </div>
            </div>
            <h1 className="text-4xl font-extrabold text-[oklch(0.14_0.02_275)] mb-2">
              System <span className="text-gradient">Status</span>
            </h1>
            <p className="text-[oklch(0.45_0.05_280)]">
              Gateway, infrastructure dependencies, worker heartbeat, and queue.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-[oklch(0.55_0.04_280)] tabular-nums">
              Last updated {formatAge(checkedAt, now)}
            </span>
            <Button id="status-refresh" variant="outline" onClick={() => void refresh()} className="rounded-xl font-semibold">
              <RefreshCw className="w-4 h-4" />
              Refresh
            </Button>
          </div>
        </div>

        {/* Overall banner */}
        <div
          className={`rounded-2xl p-5 flex items-center gap-4 border shadow-sm ${
            ok
              ? "bg-emerald-50 border-emerald-200"
              : status === "unknown"
                ? "bg-gray-50 border-gray-200"
                : "bg-red-50 border-red-200"
          }`}
        >
          {ok ? (
            <CheckCircle2 className="w-7 h-7 text-emerald-600 flex-shrink-0" />
          ) : status === "unknown" ? (
            <AlertCircle className="w-7 h-7 text-gray-500 flex-shrink-0" />
          ) : (
            <AlertCircle className="w-7 h-7 text-red-600 flex-shrink-0" />
          )}
          <div>
            <p className={`font-bold text-base ${ok ? "text-emerald-800" : status === "unknown" ? "text-gray-700" : "text-red-800"}`}>
              {ok ? "All systems operational" : status === "unknown" ? "Status unknown" : "System degraded"}
            </p>
            <p className="text-sm mt-0.5 text-[oklch(0.5_0.04_280)]">
              {mode === "ready"
                ? "Showing public readiness probe (signed out). Sign in for the full worker & queue matrix."
                : ok
                  ? "Gateway, dependencies, and worker are all healthy."
                  : "One or more components need attention."}
            </p>
          </div>
        </div>

        {/* Checks matrix */}
        <div className="glass-card rounded-2xl p-6 border border-[oklch(0.91_0.015_285)] shadow-sm">
          <h2 className="font-bold text-[oklch(0.14_0.02_275)] flex items-center gap-2 mb-4">
            <Server className="w-5 h-5 text-[oklch(0.52_0.22_155)]" />
            Gateway & Infrastructure
          </h2>
          {error && !checks && <p className="text-sm text-red-600 mb-3">{error}</p>}
          {!checks && !error && (
            <div className="flex items-center gap-2 text-sm text-[oklch(0.55_0.04_280)]">
              <Loader2 className="w-4 h-4 animate-spin text-[oklch(0.52_0.22_155)]" />
              Checking infrastructure…
            </div>
          )}
          {checks && (
            <div className="flex flex-col gap-2">
              <Row label="Gateway" value="reachable" ok />
              {Object.entries(checks).map(([key, value]) => (
                <Row key={key} label={CHECK_LABELS[key] ?? key} value={value === "ok" ? "ok" : value} ok={value === "ok"} mono={value !== "ok"} />
              ))}
            </div>
          )}
        </div>

        {/* Worker + model */}
        {health && (
          <div className="glass-card rounded-2xl p-6 border border-[oklch(0.91_0.015_285)] shadow-sm">
            <h2 className="font-bold text-[oklch(0.14_0.02_275)] flex items-center gap-2 mb-4">
              <Wifi className="w-5 h-5 text-[oklch(0.52_0.22_155)]" />
              Worker & Model
            </h2>
            <div className="flex flex-col gap-2">
              <Row
                label="Worker Alive"
                value={health.worker.alive ? "alive" : "offline"}
                ok={health.worker.alive}
              />
              <Row
                label="Last Heartbeat"
                value={formatAge(health.worker.last_heartbeat, now)}
                ok={health.worker.alive}
              />
              <Row
                label="Model Loaded"
                value={health.worker.model_loaded ? "loaded" : "not loaded"}
                ok={health.worker.model_loaded}
              />
              <Row label="Model Name" value={health.worker.model_name ?? "—"} />
              <Row label="Model Version" value={health.model_version || "—"} />
              <Row label="GPU" value={health.worker.gpu ?? "cpu"} />
            </div>
          </div>
        )}

        {/* RabbitMQ */}
        {health && (
          <div className="glass-card rounded-2xl p-6 border border-[oklch(0.91_0.015_285)] shadow-sm">
            <h2 className="font-bold text-[oklch(0.14_0.02_275)] flex items-center gap-2 mb-4">
              <Database className="w-5 h-5 text-[oklch(0.52_0.22_155)]" />
              Inference Queue
            </h2>
            <div className="flex flex-col gap-2">
              <Row label="Queue Name" value={health.rabbitmq.queue_name} mono />
              <Row
                label="Queue Depth"
                value={health.rabbitmq.queue_depth == null ? "unavailable" : String(health.rabbitmq.queue_depth)}
                ok={health.rabbitmq.queue_depth != null}
              />
            </div>
          </div>
        )}

        {/* Build info */}
        {health && (
          <div className="glass-card rounded-2xl p-6 border border-[oklch(0.91_0.015_285)] shadow-sm">
            <h2 className="font-bold text-[oklch(0.14_0.02_275)] flex items-center gap-2 mb-4">
              <GitBranch className="w-5 h-5 text-[oklch(0.52_0.22_155)]" />
              Build
            </h2>
            <div className="flex flex-col gap-2">
              <Row label="App Version" value={health.app_version || "—"} mono />
              <Row label="Git SHA" value={health.git_sha ? health.git_sha.slice(0, 12) : "n/a"} mono />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
