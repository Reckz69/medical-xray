"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { motion } from "framer-motion";
import {
  Images,
  Loader2,
  RefreshCw,
  AlertCircle,
  ChevronDown,
  Zap,
  Trash2,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Info,
  FileClock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  deleteScan,
  listScans,
  OUTPUT_TYPES,
  type Scan,
  type ScanList,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { OutputCard } from "@/components/OutputCard";
import { StatusChip } from "@/components/StatusChip";
import { ScanViewer } from "@/components/ScanViewer";
import { getSettings } from "@/lib/settings";

const PANELS = [
  { type: OUTPUT_TYPES.ORIGINAL, label: "Original Image", accentColor: "#6b7280", description: "Raw uploaded scan" },
  { type: OUTPUT_TYPES.NOISE_MAP, label: "Noise Map", accentColor: "#ef4444", description: "Isolated residual noise" },
  { type: OUTPUT_TYPES.UNET, label: "U-Net Output", accentColor: "#3b82f6", description: "N2N U-Net denoised" },
  { type: OUTPUT_TYPES.ENHANCED, label: "Enhanced Result", accentColor: "#8b5cf6", description: "Final clinical output" },
];

const PAGE_SIZE = 8;

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

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function MetaBadge({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[oklch(0.91_0.015_285)] bg-white px-2.5 py-1 text-[11px] font-medium text-[oklch(0.45_0.05_280)]">
      <span className="uppercase tracking-wider text-[10px] text-[oklch(0.55_0.04_280)]">{label}</span>
      <span className="font-semibold text-[oklch(0.14_0.02_275)]">{value}</span>
    </span>
  );
}

function ScanCard({
  scan,
  onDelete,
  confirming,
  onConfirm,
  onCancel,
  compact,
}: {
  scan: Scan;
  onDelete: (id: string) => void;
  confirming: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  compact: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const completed = scan.status === "COMPLETED";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card rounded-2xl overflow-hidden border border-[oklch(0.91_0.015_285)] shadow-sm"
    >
      <div className={`px-5 py-4 flex flex-col gap-3 ${compact ? "lg:px-4 lg:py-3" : ""}`}>
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[oklch(0.94_0.05_290)] flex items-center justify-center flex-shrink-0">
            <Images className="w-5 h-5 text-[oklch(0.44_0.22_290)]" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-bold text-[oklch(0.14_0.02_275)] text-sm truncate" id={`scan-name-${scan.id}`}>
              {scan.original_name}
            </p>
            <p className="text-xs text-[oklch(0.55_0.04_280)] mt-0.5">
              {formatDate(scan.created_at)} · {scan.format} · {scan.width}×{scan.height} px ·{" "}
              {formatBytes(scan.size_bytes)}
            </p>
          </div>
          <div className="flex items-center gap-2">
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

        {completed && (
          <div className="flex flex-wrap gap-1.5">
            <MetaBadge label="Model" value={scan.model_id ?? "n2n_unet"} />
            <MetaBadge label="Noise" value={(scan.noise_variance ?? 0).toFixed(2)} />
            {scan.processing_time_ms != null && (
              <MetaBadge label="Time" value={`${scan.processing_time_ms.toFixed(0)} ms`} />
            )}
            <MetaBadge label="Outputs" value={`${scan.outputs.length ?? 4}`} />
            {scan.was_bypassed && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">
                <CheckCircle2 className="w-3 h-3" />
                Bypassed
              </span>
            )}
          </div>
        )}

        {scan.routing_message && (
          <p className="text-xs text-[oklch(0.55_0.04_280)] flex items-start gap-1.5">
            <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            <span className="truncate">{scan.routing_message}</span>
          </p>
        )}

        {confirming ? (
          <div className="flex items-center gap-2">
            <Button
              id={`delete-confirm-${scan.id}`}
              onClick={onConfirm}
              variant="destructive"
              size="sm"
              className="rounded-lg font-semibold"
            >
              Confirm delete
            </Button>
            <Button id={`delete-cancel-${scan.id}`} onClick={onCancel} size="sm" variant="ghost" className="rounded-lg">
              Cancel
            </Button>
          </div>
        ) : (
          <button
            id={`delete-${scan.id}`}
            onClick={() => onDelete(scan.id)}
            className="self-start inline-flex items-center gap-1.5 text-xs font-semibold text-red-600 hover:text-red-700 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Delete scan
          </button>
        )}
      </div>

      {expanded && (
        <div className="border-t border-[oklch(0.91_0.015_285)] bg-[oklch(0.98_0.005_285)] p-5">
          {completed ? (
            <div className="flex flex-col gap-6">
              <ScanViewer scanId={scan.id} />
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
            </div>
          ) : (
            <div className="flex items-center gap-3 text-sm text-[oklch(0.55_0.04_280)]">
              <FileClock className="w-4 h-4 text-[oklch(0.52_0.22_290)]" />
              This scan has not finished processing yet — the list refreshes
              automatically, so check back in a moment.
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
}

export default function GalleryPage() {
  const { user, loading: authLoading } = useAuth();
  const [data, setData] = useState<ScanList | null>(null);
  const [page, setPage] = useState(0);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const confirmTimer = useRef<number | null>(null);

  const fetchPage = useCallback(
    async (pageNo: number, silent = false) => {
      if (!silent) setRefreshing(true);
      try {
        const result = await listScans(pageNo * PAGE_SIZE, PAGE_SIZE);
        setData(result);
        setError("");
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to load scans");
      } finally {
        setRefreshing(false);
      }
    },
    []
  );

  useEffect(() => {
    if (!user) return;
    const initial = window.setTimeout(() => void fetchPage(page, true), 0);
    const timer = window.setInterval(
      () => void fetchPage(page, true),
      getSettings().pollIntervalSeconds * 1000
    );
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [user, page, fetchPage]);

  useEffect(() => () => {
    if (confirmTimer.current) window.clearTimeout(confirmTimer.current);
  }, []);

  const requestDelete = (id: string) => {
    setConfirming(id);
    if (confirmTimer.current) window.clearTimeout(confirmTimer.current);
    confirmTimer.current = window.setTimeout(() => setConfirming(null), 6000);
  };

  const cancelDelete = () => {
    setConfirming(null);
    if (confirmTimer.current) window.clearTimeout(confirmTimer.current);
  };

  const handleConfirmDelete = async (id: string) => {
    setConfirming(null);
    if (confirmTimer.current) window.clearTimeout(confirmTimer.current);
    setDeleting(true);
    try {
      await deleteScan(id);
      toast.success("Scan deleted");
      if ((data?.items.length ?? 0) === 1 && page > 0) {
        setPage(page - 1);
      } else {
        void fetchPage(page, true);
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to delete scan");
    } finally {
      setDeleting(false);
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

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const compact = getSettings().gridDensity === "compact";
  const from = data ? data.offset + 1 : 0;
  const to = data ? Math.min(data.total, data.offset + data.items.length) : 0;

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
              Review, compare, download, and manage outputs from every scan you have processed.
            </p>
          </div>
          <Button
            id="refresh-gallery"
            variant="outline"
            onClick={() => void fetchPage(page)}
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

        {!error && data === null && (
          <div className="flex flex-col items-center gap-4 py-20 text-center">
            <Loader2 className="w-8 h-8 text-[oklch(0.52_0.22_290)] animate-spin" />
            <p className="text-sm text-[oklch(0.55_0.04_280)]">Loading your scans…</p>
          </div>
        )}

        {!error && data && data.items.length === 0 && (
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

        {!error && data && data.items.length > 0 && (
          <>
            <div className={`flex flex-col gap-4 ${compact ? "gap-3" : ""}`}>
              {data.items.map((scan) => (
                <ScanCard
                  key={scan.id}
                  scan={scan}
                  compact={compact}
                  onDelete={requestDelete}
                  confirming={confirming === scan.id}
                  onConfirm={() => void handleConfirmDelete(scan.id)}
                  onCancel={cancelDelete}
                />
              ))}
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between">
              <p className="text-xs text-[oklch(0.55_0.04_280)] tabular-nums">
                Showing {from}–{to} of {data.total}
              </p>
              <div className="flex items-center gap-2">
                <Button
                  id="gallery-prev"
                  variant="outline"
                  size="sm"
                  disabled={page === 0 || deleting}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  className="rounded-lg"
                >
                  <ChevronLeft className="w-4 h-4" />
                  Prev
                </Button>
                <span className="text-xs text-[oklch(0.55_0.04_280)] tabular-nums">
                  Page {page + 1} / {totalPages}
                </span>
                <Button
                  id="gallery-next"
                  variant="outline"
                  size="sm"
                  disabled={page + 1 >= totalPages || deleting}
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  className="rounded-lg"
                >
                  Next
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
