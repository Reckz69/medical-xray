"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  CircleDollarSign,
  Database,
  Images,
  LayoutDashboard,
  Loader2,
  RefreshCw,
  Server,
  Wifi,
  WifiOff,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { useLiveScans } from "@/lib/useLiveScans";
import { useInfraHealth } from "@/lib/useInfraHealth";
import { StatusChip } from "@/components/StatusChip";
import { getSettings } from "@/lib/settings";
import { SCAN_STATUS, type Scan } from "@/lib/api";

const CHECK_LABELS: Record<string, string> = {
  postgres: "PostgreSQL",
  redis: "Redis",
  rabbitmq: "RabbitMQ",
  storage: "Object Storage (MinIO)",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function StatCard({
  label,
  value,
  sub,
  tone = "default",
  icon,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "default" | "ok" | "warn" | "error";
  icon?: React.ReactNode;
}) {
  const toneText =
    tone === "ok"
      ? "text-emerald-600"
      : tone === "warn"
        ? "text-amber-600"
        : tone === "error"
          ? "text-red-600"
          : "text-gradient";
  return (
    <div className="glass-card rounded-2xl p-5 border border-[oklch(0.91_0.015_285)] shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[11px] uppercase tracking-wider font-semibold text-[oklch(0.55_0.04_280)]">
          {label}
        </p>
        {icon && <div className="w-8 h-8 rounded-lg bg-[oklch(0.94_0.05_155)] flex items-center justify-center text-[oklch(0.44_0.22_155)]">{icon}</div>}
      </div>
      <p className={`text-2xl font-extrabold leading-tight ${toneText}`}>{value}</p>
      {sub && <p className="text-xs text-[oklch(0.55_0.04_280)] mt-1">{sub}</p>}
    </div>
  );
}

function RecentScans({ scans }: { scans: Scan[] }) {
  const recent = scans.slice(0, 6);
  if (recent.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-10 text-center">
        <Images className="w-8 h-8 text-[oklch(0.78_0.04_285)]" />
        <p className="text-sm text-[oklch(0.55_0.04_280)]">No scans yet.</p>
        <Link href="/denoise">
          <Button className="btn-purple rounded-xl font-semibold">Upload your first X-ray</Button>
        </Link>
      </div>
    );
  }
  return (
    <div className="flex flex-col">
      {recent.map((scan, i) => (
        <div
          key={scan.id}
          className={`flex items-center gap-3 py-2.5 ${i > 0 ? "border-t border-[oklch(0.94_0.02_285)]" : ""}`}
        >
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-[oklch(0.14_0.02_275)] truncate">
              {scan.original_name}
            </p>
            <p className="text-xs text-[oklch(0.55_0.04_280)] mt-0.5">
              {new Date(scan.created_at).toLocaleDateString()} · {formatBytes(scan.size_bytes)}
            </p>
          </div>
          <StatusChip status={scan.status} />
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const { user, loading: authLoading } = useAuth();
  const { scans, total, loading, lastUpdated: scansUpdated, refresh: refreshScans } = useLiveScans(50);
  const {
    health,
    ready,
    mode,
    error: infraError,
    lastUpdated: infraUpdated,
    refresh: refreshInfra,
  } = useInfraHealth(15_000);

  const [now, setNow] = useState<number>(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const refreshAll = useCallback(() => {
    void refreshScans();
    void refreshInfra();
  }, [refreshScans, refreshInfra]);

  const completed = scans.filter((s) => s.status === SCAN_STATUS.COMPLETED);
  const inProgress = scans.filter(
    (s) =>
      s.status === SCAN_STATUS.QUEUED ||
      s.status === SCAN_STATUS.RUNNING ||
      s.status === "RETRYING"
  );
  const failedCancelled = scans.filter(
    (s) => s.status === SCAN_STATUS.FAILED || s.status === SCAN_STATUS.CANCELLED
  );
  const bypassed = completed.filter((s) => s.was_bypassed);
  const storageBytes = scans.reduce((sum, s) => sum + s.size_bytes, 0);
  const avgProcessing =
    completed.filter((s) => s.processing_time_ms != null).length > 0
      ? Math.round(
          completed.reduce((sum, s) => sum + (s.processing_time_ms ?? 0), 0) /
            completed.filter((s) => s.processing_time_ms != null).length
        )
      : null;

  const checks = health?.checks ?? ready?.checks ?? null;
  const infraHealthy = health?.status === "ok" || ready?.status === "ok";
  const workerAlive = health?.worker.alive ?? false;
  const lastChecked = health?.checked_at ?? infraUpdated?.toISOString() ?? null;
  const checkedAge = lastChecked ? Math.max(0, Math.round((now - new Date(lastChecked).getTime()) / 1000)) : null;
  const scansAge = scansUpdated ? Math.max(0, Math.round((now - scansUpdated.getTime()) / 1000)) : null;

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
            <LayoutDashboard className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-2xl font-extrabold text-[oklch(0.14_0.02_275)] mb-2">
            Sign in to view your <span className="text-gradient">dashboard</span>
          </h1>
          <p className="text-[oklch(0.55_0.04_280)] text-sm mb-6">
            Track scans, queue, worker status, and infrastructure health.
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

  const density = getSettings().gridDensity;

  return (
    <div className="min-h-screen bg-[oklch(0.98_0.005_285)] orb-bg pb-20">
      <div className={`max-w-7xl mx-auto px-6 md:px-12 py-12 flex flex-col gap-8 ${density === "compact" ? "gap-6" : ""}`}>
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-3">
              <div className="pill-badge">
                <Activity className="w-3 h-3" />
                Operations
              </div>
            </div>
            <h1 className="text-4xl font-extrabold text-[oklch(0.14_0.02_275)] mb-2">
              <span className="text-gradient">Dashboard</span>
            </h1>
            <p className="text-[oklch(0.45_0.05_280)]">
              Live overview of your scans, queue, and infrastructure health.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-[oklch(0.55_0.04_280)] tabular-nums">
              Updated {scansAge != null ? `${scansAge}s ago` : "—"}
            </span>
            <Button
              id="dashboard-refresh"
              variant="outline"
              onClick={refreshAll}
              className="rounded-xl font-semibold"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh
            </Button>
          </div>
        </div>

        {/* Summary cards */}
        <div className={`grid grid-cols-2 ${density === "compact" ? "lg:grid-cols-4 md:grid-cols-4 gap-3" : "lg:grid-cols-4 gap-5"}`}>
          <StatCard
            label="Infrastructure"
            value={infraHealthy ? "Healthy" : "Degraded"}
            sub={mode === "ready" ? "public probe" : `${Object.keys(checks ?? {}).length} services checked`}
            tone={infraHealthy ? "ok" : "error"}
            icon={infraHealthy ? <Wifi className="w-4 h-4" /> : <WifiOff className="w-4 h-4" />}
          />
          <StatCard
            label="Total Scans"
            value={loading ? "…" : String(total)}
            sub={`${completed.length} completed`}
            icon={<Images className="w-4 h-4" />}
          />
          <StatCard
            label="In Progress"
            value={String(inProgress.length)}
            sub="queued · running · retrying"
            tone={inProgress.length > 0 ? "warn" : "default"}
            icon={<Zap className="w-4 h-4" />}
          />
          <StatCard
            label="Failed / Cancelled"
            value={String(failedCancelled.length)}
            sub="needs attention"
            tone={failedCancelled.length > 0 ? "error" : "default"}
            icon={<AlertCircle className="w-4 h-4" />}
          />
        </div>

        {/* Worker + queue row */}
        <div className={`grid grid-cols-1 md:grid-cols-3 gap-5 ${density === "compact" ? "gap-3" : ""}`}>
          <StatCard
            label="Worker"
            value={workerAlive ? "Alive" : "Offline"}
            sub={
              health?.worker.last_heartbeat
                ? `last heartbeat ${Math.max(0, Math.round((now - new Date(health.worker.last_heartbeat).getTime()) / 1000))}s ago`
                : undefined
            }
            tone={workerAlive ? "ok" : "error"}
            icon={<Server className="w-4 h-4" />}
          />
          <StatCard
            label="Model"
            value={health?.worker.model_name ?? "n2n_unet"}
            sub={health?.model_version ? `version ${health.model_version}` : "version unknown"}
            icon={<Database className="w-4 h-4" />}
          />
          <StatCard
            label="Queue Depth"
            value={health?.rabbitmq.queue_depth == null ? "n/a" : String(health.rabbitmq.queue_depth)}
            sub={health?.rabbitmq.queue_name ?? "inference.worker"}
            tone={(health?.rabbitmq.queue_depth ?? 0) > 0 ? "warn" : "default"}
            icon={<CircleDollarSign className="w-4 h-4" />}
          />
        </div>

        {/* Health matrix + Recent scans */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="glass-card rounded-2xl p-6 border border-[oklch(0.91_0.015_285)] shadow-sm">
            <h2 className="font-bold text-[oklch(0.14_0.02_275)] flex items-center gap-2 mb-4">
              <Activity className="w-5 h-5 text-[oklch(0.52_0.22_155)]" />
              Infrastructure Health
            </h2>
            {infraError && !checks && (
              <p className="text-sm text-red-600">{infraError}</p>
            )}
            {checks && (
              <div className="flex flex-col gap-2">
                {Object.entries(checks).map(([key, value]) => {
                  const ok = value === "ok";
                  return (
                    <div key={key} className="flex items-center justify-between px-3 py-2.5 rounded-xl bg-[oklch(0.97_0.01_285)]">
                      <span className="text-sm font-medium text-[oklch(0.35_0.05_280)]">
                        {CHECK_LABELS[key] ?? key}
                      </span>
                      <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full border ${
                        ok ? "bg-emerald-50 border-emerald-200 text-emerald-700" : "bg-red-50 border-red-200 text-red-700"
                      }`}>
                        {ok ? <CheckCircle2 className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                        {ok ? "ok" : value}
                      </span>
                    </div>
                  );
                })}
                <div className="flex flex-wrap items-center gap-x-5 gap-y-1 mt-3 px-1 text-xs text-[oklch(0.55_0.04_280)]">
                  {health && (
                    <>
                      <span>app v{health.app_version}</span>
                      <span className="font-mono">sha {health.git_sha ? health.git_sha.slice(0, 8) : "n/a"}</span>
                    </>
                  )}
                  <span>checked {checkedAge != null ? `${checkedAge}s ago` : "—"}</span>
                </div>
              </div>
            )}
            {!checks && !infraError && (
              <div className="flex items-center gap-2 text-sm text-[oklch(0.55_0.04_280)]">
                <Loader2 className="w-4 h-4 animate-spin text-[oklch(0.52_0.22_155)]" />
                Checking infrastructure…
              </div>
            )}
          </div>

          <div className="glass-card rounded-2xl p-6 border border-[oklch(0.91_0.015_285)] shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-bold text-[oklch(0.14_0.02_275)] flex items-center gap-2">
                <Images className="w-5 h-5 text-[oklch(0.52_0.22_155)]" />
                Recent Scans
              </h2>
              <Link href="/gallery" className="text-sm font-semibold text-[oklch(0.44_0.22_155)] hover:text-[oklch(0.36_0.20_155)] transition-colors">
                View all →
              </Link>
            </div>
            <RecentScans scans={scans} />
          </div>
        </div>

        {/* Statistics */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          {[
            { label: "Avg Processing", value: avgProcessing != null ? `${avgProcessing} ms` : "—" },
            { label: "Bypassed (clean)", value: String(bypassed.length) },
            { label: "Storage Used", value: formatBytes(storageBytes) },
            { label: "Recent Failure Rate", value: scans.length ? `${Math.round((failedCancelled.length / scans.length) * 100)}%` : "—" },
          ].map((s) => (
            <div key={s.label} className="stat-card !py-4">
              <div className="text-base font-bold text-gradient mb-1 leading-tight">{s.value}</div>
              <div className="text-[11px] text-[oklch(0.55_0.04_280)] uppercase tracking-wider">{s.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
