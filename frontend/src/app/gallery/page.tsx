"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Images,
  Loader2,
  RefreshCw,
  AlertCircle,
  ChevronDown,
  Zap,
  Clock,
  CheckCircle2,
} from "lucide-react";import { Button } from "@/components/ui/button";
import { listScans, OUTPUT_TYPES, type Scan } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { OutputCard } from "@/components/OutputCard";

const PANELS = [
  { type: OUTPUT_TYPES.ORIGINAL, label: "Original Image", accentColor: "#6b7280", description: "Raw uploaded scan" },
  { type: OUTPUT_TYPES.NOISE_MAP, label: "Noise Map", accentColor: "#ef4444", description: "Isolated residual noise" },
  { type: OUTPUT_TYPES.UNET, label: "U-Net Output", accentColor: "#3b82f6", description: "N2N U-Net denoised" },
  { type: OUTPUT_TYPES.ENHANCED, label: "Enhanced Result", accentColor: "#8b5cf6", description: "Final clinical output" },
];

function StatusChip({ status }: { status: string }) {
  const styles: Record<string, string> = {
    COMPLETED: "bg-emerald-50 border-emerald-200 text-emerald-700",
    RUNNING: "bg-blue-50 border-blue-200 text-blue-700",
    QUEUED: "bg-amber-50 border-amber-200 text-amber-700",
    FAILED: "bg-red-50 border-red-200 text-red-700",
    CANCELLED: "bg-red-50 border-red-200 text-red-700",
  };
  const Icon = status === "COMPLETED" ? CheckCircle2 : status === "QUEUED" || status === "RUNNING" ? Clock : AlertCircle;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-full border ${styles[status] ?? "bg-gray-50 border-gray-200 text-gray-600"}`}>
      <Icon className="w-3 h-3" />
      {status}
    </span>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function ScanCard({ scan }: { scan: Scan }) {
  const [expanded, setExpanded] = useState(false);
  const completed = scan.status === "COMPLETED";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card rounded-2xl overflow-hidden border border-[oklch(0.91_0.015_285)] shadow-sm"
    >
      <div className="px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-[oklch(0.94_0.05_290)] flex items-center justify-center flex-shrink-0">
          <Images className="w-5 h-5 text-[oklch(0.44_0.22_290)]" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-bold text-[oklch(0.14_0.02_275)] text-sm truncate" id={`scan-name-${scan.id}`}>
            {scan.original_name}
          </p>
          <p className="text-xs text-[oklch(0.55_0.04_280)] mt-0.5">
            {formatDate(scan.created_at)} · {scan.format} · {scan.width}×{scan.height} px ·{" "}
            {(scan.size_bytes / 1024).toFixed(0)} KB
          </p>
        </div>
        <div className="flex items-center gap-3">
          <StatusChip status={scan.status} />
          <button
            id={`expand-${scan.id}`}
            onClick={() => setExpanded((v) => !v)}
            className="inline-flex items-center gap-1.5 text-xs font-bold text-[oklch(0.44_0.22_155)] hover:text-[oklch(0.36_0.20_155)] transition-colors"
          >
            {expanded ? "Hide" : "View & Download"}
            <ChevronDown className={`w-4 h-4 transition-transform ${expanded ? "rotate-180" : ""}`} />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-[oklch(0.91_0.015_285)] bg-[oklch(0.98_0.005_285)] p-5">
          {completed ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-8">
              {PANELS.map((panel) => (
                <OutputCard
                  key={`${scan.id}-${panel.type}`}
                  scanId={scan.id}
                  outputType={panel.type}
                  label={panel.label}
                  accentColor={panel.accentColor}
                  description={panel.description}
                  enabled
                  isScanning={false}
                />
              ))}
            </div>
          ) : (
            <div className="flex items-center gap-3 text-sm text-[oklch(0.55_0.04_280)]">
              <Loader2 className="w-4 h-4 animate-spin text-[oklch(0.52_0.22_290)]" />
              This scan has not finished processing yet. Polling is disabled here — refresh the list in a moment.
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
}

export default function GalleryPage() {
  const { user, loading: authLoading } = useAuth();
  const [scans, setScans] = useState<Scan[] | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const fetchScans = useCallback(async () => {
    try {
      const result = await listScans(0, 50);
      setScans(result.items);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load scans");
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    const timer = window.setTimeout(() => void fetchScans(), 0);
    return () => window.clearTimeout(timer);
  }, [user, fetchScans]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await fetchScans();
    } finally {
      setRefreshing(false);
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-[oklch(0.98_0.005_285)] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-[oklch(0.52_0.22_290)] animate-spin" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-[oklch(0.98_0.005_285)] orb-bg flex items-center justify-center px-6">
        <div className="glass-card rounded-2xl p-10 max-w-md text-center shadow-sm border border-[oklch(0.91_0.015_285)]">
          <h1 className="text-2xl font-extrabold text-[oklch(0.14_0.02_275)] mb-2">
            Sign in to view your <span className="text-gradient">gallery</span>
          </h1>
          <p className="text-[oklch(0.55_0.04_280)] text-sm mb-6">
            Your processed scans live in a private gallery tied to your account.
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

  return (
    <div className="min-h-screen bg-[oklch(0.98_0.005_285)] orb-bg pb-20">
      <div className="max-w-6xl mx-auto px-6 md:px-12 py-12 flex flex-col gap-8">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-3">
              <div className="pill-badge">
                <Zap className="w-3 h-3" />
                Results Gallery
              </div>
            </div>
            <h1 className="text-4xl font-extrabold text-[oklch(0.14_0.02_275)] mb-2">
              Your <span className="text-gradient">Scans</span>
            </h1>
            <p className="text-[oklch(0.45_0.05_280)]">
              Review and download outputs from every scan you have processed.
            </p>
          </div>
          <Button
            id="refresh-gallery"
            variant="outline"
            onClick={() => void handleRefresh()}
            disabled={refreshing}
            className="rounded-xl font-semibold"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>

        {error && (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-5 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-bold text-red-800 text-sm mb-0.5">Could not load your scans</p>
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        )}

        {!error && scans === null && (
          <div className="flex flex-col items-center gap-4 py-20 text-center">
            <Loader2 className="w-8 h-8 text-[oklch(0.52_0.22_290)] animate-spin" />
            <p className="text-sm text-[oklch(0.55_0.04_280)]">Loading your scans…</p>
          </div>
        )}

        {!error && scans && scans.length === 0 && (
          <div className="glass-card rounded-2xl p-14 text-center border border-[oklch(0.91_0.015_285)] shadow-sm">
            <div className="w-14 h-14 rounded-2xl btn-purple flex items-center justify-center mx-auto mb-4">
              <Images className="w-7 h-7 text-white" />
            </div>
            <h2 className="text-xl font-extrabold text-[oklch(0.14_0.02_275)] mb-2">No scans yet</h2>
            <p className="text-sm text-[oklch(0.55_0.04_280)] mb-6">
              Upload your first chest X-ray and your results will appear here.
            </p>
            <Link href="/denoise" className="inline-block">
              <Button id="empty-go-denoise" className="btn-purple rounded-xl px-8 h-11 font-bold">
                Go to Upload
              </Button>
            </Link>
          </div>
        )}

        {!error && scans && scans.length > 0 && (
          <div className="flex flex-col gap-4">
            {scans.map((scan) => (
              <ScanCard key={scan.id} scan={scan} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
