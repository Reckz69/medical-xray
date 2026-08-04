"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";
import {
  Upload,
  Zap,
  X,
  FileImage,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  Info,
  BarChart3,
  RefreshCw,
  Wifi,
  WifiOff,
  Maximize2,
  Loader2,
} from "lucide-react";
import {
  checkHealth,
  uploadScan,
  pollJob,
  getScan,
  OUTPUT_TYPES,
  isScanTerminal,
  type Job,
  type Scan,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { OutputCard } from "@/components/OutputCard";

/* ============================================
   TYPES
   ============================================ */
type Phase = "idle" | "uploading" | "processing" | "done" | "error";

const RESULT_PANELS = [
  { type: OUTPUT_TYPES.ORIGINAL, label: "Original Image", accentColor: "#6b7280", description: "Raw uploaded scan" },
  { type: OUTPUT_TYPES.NOISE_MAP, label: "Noise Map", accentColor: "#ef4444", description: "Isolated residual noise" },
  { type: OUTPUT_TYPES.UNET, label: "U-Net Output", accentColor: "#3b82f6", description: "N2N U-Net denoised" },
  { type: OUTPUT_TYPES.ENHANCED, label: "Enhanced Result", accentColor: "#8b5cf6", description: "Final clinical output" },
];

async function waitForScanTerminal(scanId: string, timeoutMs = 300_000): Promise<Scan> {
  const deadline = Date.now() + timeoutMs;
  let current = await getScan(scanId);
  while (!isScanTerminal(current.status) && Date.now() < deadline) {
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
    current = await getScan(scanId);
  }
  return current;
}

/* ============================================
   UPLOAD ZONE
   ============================================ */
function UploadZone({
  onFile,
  file,
  onClear,
  disabled,
}: {
  onFile: (f: File) => void;
  file: File | null;
  onClear: () => void;
  disabled: boolean;
}) {
  const onDrop = useCallback(
    (accepted: File[]) => { if (accepted[0]) onFile(accepted[0]); },
    [onFile]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "image/*": [".png", ".jpg", ".jpeg"],
      "application/dicom": [".dcm", ".dicom"],
    },
    maxFiles: 1,
    disabled: !!file || disabled,
  });

  if (file) {
    return (
      <div className="rounded-2xl border border-[oklch(0.78_0.14_290)] bg-[oklch(0.97_0.01_285)] p-5 flex items-center gap-4">
        <div className="w-11 h-11 rounded-xl bg-[oklch(0.94_0.05_290)] flex items-center justify-center flex-shrink-0">
          <FileImage className="w-5 h-5 text-[oklch(0.44_0.22_290)]" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-[oklch(0.14_0.02_275)] text-sm truncate">{file.name}</p>
          <p className="text-xs text-[oklch(0.55_0.04_280)] mt-0.5">
            {(file.size / 1024 / 1024).toFixed(2)} MB ·{" "}
            {file.name.toLowerCase().endsWith(".dcm") || file.name.toLowerCase().endsWith(".dicom")
              ? "DICOM"
              : "Image"}
          </p>
        </div>
        <button
          id="clear-file-btn"
          onClick={onClear}
          disabled={disabled}
          className="w-8 h-8 rounded-lg hover:bg-red-50 disabled:opacity-50 flex items-center justify-center text-[oklch(0.55_0.04_280)] hover:text-red-500 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <div
      {...getRootProps()}
      id="drop-zone"
      className={`
        relative rounded-2xl border-2 border-dashed transition-all duration-200
        p-10 flex flex-col items-center justify-center gap-4 text-center
        ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
        ${isDragActive
          ? "border-[oklch(0.52_0.22_290)] bg-[oklch(0.94_0.05_290)]"
          : "border-[oklch(0.88_0.09_290)] bg-[oklch(0.98_0.005_285)] hover:border-[oklch(0.68_0.18_290)] hover:bg-[oklch(0.96_0.02_285)]"
        }
      `}
    >
      <input {...getInputProps()} id="file-input" />
      <div className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all
        ${isDragActive ? "bg-[oklch(0.52_0.22_290)] scale-110" : "bg-[oklch(0.94_0.05_290)]"}`}>
        <Upload className={`w-6 h-6 transition-colors ${isDragActive ? "text-white" : "text-[oklch(0.52_0.22_290)]"}`} />
      </div>
      <div>
        <p className="text-[oklch(0.14_0.02_275)] font-semibold text-base">
          {isDragActive ? "Drop your X-ray here" : "Upload X-ray or DICOM"}
        </p>
        <p className="text-sm text-[oklch(0.55_0.04_280)] mt-1">
          Drag & drop or click · PNG, JPG, DCM, DICOM
        </p>
      </div>
    </div>
  );
}

/* ============================================
   BACKEND STATUS BADGE
   ============================================ */
function BackendStatus({ online }: { online: boolean | null }) {
  if (online === null) return null;
  return (
    <div className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1 rounded-full border ${
      online
        ? "bg-emerald-50 border-emerald-200 text-emerald-700"
        : "bg-red-50 border-red-200 text-red-700"
    }`}>
      {online ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
      {online ? "Backend Online" : "Backend Offline"}
    </div>
  );
}

/* ============================================
   PROCESSING STATUS CARD
   ============================================ */
function ProcessingCard({ job, phase }: { job: Job | null; phase: Phase }) {
  const status = job?.scan_status ?? null;
  const running = status === "QUEUED" || status === "RUNNING" || status === "RETRYING";
  const message =
    phase === "uploading"
      ? "Uploading & validating your X-ray…"
      : status === "QUEUED"
        ? "Queued — waiting for the inference worker…"
        : status === "RETRYING"
          ? `Retrying (attempt ${job?.attempt ?? 1}/${job?.max_attempts ?? 3})…`
          : "Running — N2N U-Net analyzing & enhancing…";

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-5">
      <div className="flex items-center gap-3 text-sm text-[oklch(0.52_0.22_290)] font-medium">
        <Loader2 className="w-4 h-4 animate-spin" />
        {message}
      </div>
      {running && (
        <div className="mt-3 h-1.5 w-full rounded-full bg-[oklch(0.94_0.05_290)] overflow-hidden">
          <div className="h-full rounded-full bg-[oklch(0.52_0.22_290)] animate-progress-indeterminate" />
        </div>
      )}
    </motion.div>
  );
}

/* ============================================
   ROUTING BANNER
   ============================================ */
function RoutingBanner({ scan }: { scan: Scan }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`rounded-xl p-4 flex items-start gap-3 border mb-6 shadow-sm ${
        scan.was_bypassed
          ? "bg-emerald-50 border-emerald-200"
          : "bg-[oklch(0.96_0.02_290)] border-[oklch(0.88_0.09_290)]"
      }`}
    >
      {scan.was_bypassed
        ? <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
        : <Zap className="w-5 h-5 text-[oklch(0.52_0.22_290)] flex-shrink-0 mt-0.5" />
      }
      <div>
        <p className={`font-semibold text-sm ${scan.was_bypassed ? "text-emerald-800" : "text-[oklch(0.35_0.12_285)]"}`}>
          {scan.routing_message ?? "Processing complete"}
        </p>
        <p className="text-xs mt-0.5 text-[oklch(0.55_0.04_280)]">
          Measured flat-tissue noise variance: <strong>{(scan.noise_variance ?? 0).toFixed(2)}</strong>
          {" · "}Image: {scan.width} × {scan.height} px
        </p>
      </div>
    </motion.div>
  );
}

/* ============================================
   DENOISE PAGE
   ============================================ */
export default function DenoisePage() {
  const { user, loading: authLoading } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [job, setJob] = useState<Job | null>(null);
  const [scan, setScan] = useState<Scan | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [duplicateMsg, setDuplicateMsg] = useState<string | null>(null);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const pollRef = useRef<{ cancel: () => void } | null>(null);

  const checkBackend = useCallback(async () => {
    const ok = await checkHealth();
    setBackendOnline(ok);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void checkBackend(), 0);
    return () => window.clearTimeout(timer);
  }, [checkBackend]);

  useEffect(() => () => { pollRef.current?.cancel(); }, []);

  const handleFile = (f: File) => {
    setFile(f);
    setLocalPreview(URL.createObjectURL(f));
    setScan(null);
    setErrorMsg("");
    setDuplicateMsg(null);
    setPhase("idle");
  };

  const handleClear = () => {
    pollRef.current?.cancel();
    setFile(null);
    setLocalPreview(null);
    setScan(null);
    setJob(null);
    setErrorMsg("");
    setDuplicateMsg(null);
    setPhase("idle");
  };

  const handleProcess = async () => {
    if (!file) return;
    pollRef.current?.cancel();
    setScan(null);
    setJob(null);
    setErrorMsg("");
    setDuplicateMsg(null);
    setPhase("uploading");

    try {
      const upload = await uploadScan(file);
      const scanId = upload.scan.id;

      // Duplicate bytes already uploaded in this org: no job is queued. Show
      // the existing result (waiting for it if it is still being processed).
      if (upload.duplicate) {
        setDuplicateMsg(upload.message ?? "This image has already been uploaded.");
        setPhase("processing");
        const existing = await waitForScanTerminal(scanId);
        setScan(existing);
        setPhase("done");
        setBackendOnline(true);
        return;
      }

      const jobId = upload.job_id;
      if (!jobId) {
        throw new Error("Upload returned no job to poll");
      }

      const poll = pollJob(
        jobId,
        (updated) => {
          setJob(updated);
          if (!isScanTerminal(updated.scan_status)) setPhase("processing");
        },
        { timeoutMs: 300_000 }
      );
      pollRef.current = poll;

      const finished = await poll.promise;
      pollRef.current = null;

      if (finished.scan_status === "COMPLETED") {
        const scanDetail = await getScan(scanId);
        setScan(scanDetail);
        setPhase("done");
        setBackendOnline(true);
      } else {
        setErrorMsg(finished.error ?? `Scan ended with status ${finished.scan_status}`);
        setPhase("error");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error occurred";
      setErrorMsg(msg);
      setPhase("error");
    }
  };

  const isProcessing = phase === "uploading" || phase === "processing";
  const isDone = phase === "done";
  const isError = phase === "error";

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
          <div className="w-12 h-12 rounded-2xl btn-purple flex items-center justify-center mx-auto mb-4">
            <Zap className="w-6 h-6 text-white" strokeWidth={2.5} />
          </div>
          <h1 className="text-2xl font-extrabold text-[oklch(0.14_0.02_275)] mb-2">
            Sign in to use <span className="text-gradient">Denoise X</span>
          </h1>
          <p className="text-[oklch(0.55_0.04_280)] text-sm mb-6">
            Uploading X-rays requires an account so your scans and results stay private.
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
      <div className="max-w-7xl mx-auto px-6 md:px-12 py-12 flex flex-col gap-10">

        {/* Header */}
        <div>
          <div className="flex items-center gap-3 mb-4">
            <div className="pill-badge">
              <Zap className="w-3 h-3" />
              AI Inference Engine
            </div>
            <BackendStatus online={backendOnline} />
          </div>
          <h1 className="text-4xl font-extrabold text-[oklch(0.14_0.02_275)] mb-3">
            Use <span className="text-gradient">Denoise X</span>
          </h1>
          <p className="text-[oklch(0.45_0.05_280)] text-lg max-w-2xl">
            Upload your chest X-ray (DICOM, PNG, or JPEG) and the N2N U-Net engine
            delivers clinical outputs in seconds.
          </p>
        </div>

        {/* ── Top Section: Upload & Info ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div className="glass-card rounded-2xl p-6 shadow-sm border border-[oklch(0.91_0.015_285)]">
            <h2 className="font-bold text-[oklch(0.14_0.02_275)] mb-4 flex items-center gap-2">
              <Upload className="w-5 h-5 text-[oklch(0.52_0.22_290)]" />
              Upload Image
            </h2>
            <UploadZone
              onFile={handleFile}
              file={file}
              onClear={handleClear}
              disabled={isProcessing}
            />

            {file && !isProcessing && (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                <Button
                  id="process-btn"
                  className="btn-purple w-full h-12 mt-5 rounded-xl text-base font-bold gap-2 shadow-lg shadow-purple-500/20"
                  onClick={() => void handleProcess()}
                >
                  {isDone ? (
                    <><RefreshCw className="w-4 h-4" /> Re-process</>
                  ) : (
                    <><Zap className="w-4 h-4" /> Enhance X-Ray <ArrowRight className="w-4 h-4" /></>
                  )}
                </Button>
              </motion.div>
            )}

            {isProcessing && <ProcessingCard job={job} phase={phase} />}
          </div>

          <div className="flex flex-col gap-6">
            <div className="glass-card rounded-2xl p-6 space-y-4 border border-[oklch(0.91_0.015_285)] shadow-sm">
              <h3 className="font-bold text-[oklch(0.14_0.02_275)] flex items-center gap-2 text-sm">
                <Info className="w-4 h-4 text-[oklch(0.52_0.22_290)]" />
                Pipeline Steps
              </h3>
              {[
                { step: "1", text: "Smart Gateway measures noise variance in flat tissue" },
                { step: "2", text: "N2N U-Net denoising isolated residual noise map" },
                { step: "3", text: "CLAHE + soft unsharp masking applied to final output" },
              ].map((s) => (
                <div key={s.step} className="flex items-start gap-3">
                  <span className="w-5 h-5 rounded-full bg-[oklch(0.94_0.05_290)] text-[oklch(0.44_0.22_290)] text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                    {s.step}
                  </span>
                  <p className="text-sm text-[oklch(0.45_0.05_280)] leading-relaxed">{s.text}</p>
                </div>
              ))}
            </div>

            {isDone && scan && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="glass-card rounded-2xl p-5 border border-[oklch(0.91_0.015_285)] shadow-sm"
              >
                <h3 className="font-bold text-[oklch(0.14_0.02_275)] flex items-center gap-2 text-sm mb-4">
                  <BarChart3 className="w-4 h-4 text-[oklch(0.52_0.22_290)]" />
                  Inference Report
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { label: "Routing", value: scan.was_bypassed ? "Bypassed" : "Processed" },
                    { label: "Noise Var.", value: (scan.noise_variance ?? 0).toFixed(2) },
                    { label: "Enhancement", value: "CLAHE+USM" },
                    { label: "Time", value: `${(scan.processing_time_ms ?? 0).toFixed(0)} ms` },
                  ].map((s) => (
                    <div key={s.label} className="stat-card !py-3 !px-3 flex flex-col items-center justify-center text-center">
                      <div className="font-bold text-gradient text-sm md:text-base leading-tight">{s.value}</div>
                      <div className="text-[10px] md:text-xs text-[oklch(0.55_0.04_280)] mt-1 uppercase tracking-wider">{s.label}</div>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </div>
        </div>

        {/* ── Error State ── */}
        {isError && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="rounded-2xl border border-red-200 bg-red-50 p-6 flex items-start gap-4">
            <AlertCircle className="w-6 h-6 text-red-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-bold text-red-800 text-base mb-1">Processing Failed</p>
              <p className="text-sm text-red-700">{errorMsg}</p>
              <p className="text-xs text-red-600 mt-2">
                Make sure the backend and worker are running, then try again.
              </p>
            </div>
          </motion.div>
        )}

        {/* ── Routing Banner ── */}
        {isDone && scan && <RoutingBanner scan={scan} />}

        {/* ── Duplicate Notice ── */}
        {isDone && duplicateMsg && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-xl p-4 flex items-start gap-3 border border-amber-200 bg-amber-50 mb-6 shadow-sm"
          >
            <Info className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-sm text-amber-800">{duplicateMsg}</p>
              <p className="text-xs mt-0.5 text-amber-700">
                No new job was queued — showing the existing result from your library.
              </p>
            </div>
          </motion.div>
        )}

        {/* ── Bottom Section: 4 Output Cards ── */}
        {(isDone || isProcessing || (file && phase === "idle")) && (
          <div className="flex flex-col gap-4">
            <h2 className="text-2xl font-bold text-[oklch(0.14_0.02_275)] flex items-center gap-3">
              <Maximize2 className="w-6 h-6 text-[oklch(0.52_0.22_290)]" />
              Analysis Results
            </h2>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-8">
              {RESULT_PANELS.map((panel) => (
                <OutputCard
                  key={`${scan?.id ?? ""}-${panel.type}`}
                  scanId={scan?.id ?? ""}
                  outputType={panel.type}
                  label={panel.label}
                  accentColor={panel.accentColor}
                  description={panel.description}
                  fallbackImage={panel.type === OUTPUT_TYPES.ORIGINAL ? localPreview : null}
                  enabled={isDone && !!scan}
                  isScanning={isProcessing && panel.type !== OUTPUT_TYPES.ORIGINAL}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
