"use client";

import { useState, useCallback, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import { Button } from "@/components/ui/button";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload,
  ImageIcon,
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
} from "lucide-react";
import { denoiseImage, DenoiseResponse, checkHealth } from "@/lib/api";

/* ============================================
   TYPES
   ============================================ */
type AnimationStage =
  | "idle"
  | "scanning_original"
  | "scanning_noise"
  | "done"
  | "error";

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
   SCANNING LASER ANIMATION
   ============================================ */
const ScanningLaser = ({ color }: { color: string }) => (
  <>
    <motion.div
      className="absolute left-0 right-0 h-1 z-20"
      style={{
        background: `linear-gradient(90deg, transparent 0%, ${color} 50%, transparent 100%)`,
        boxShadow: `0 0 20px ${color}, 0 0 40px ${color}`,
      }}
      initial={{ top: '0%' }}
      animate={{ top: '100%' }}
      transition={{
        duration: 2,
        repeat: Infinity,
        repeatType: 'reverse',
        ease: 'easeInOut',
      }}
    />
    <motion.div
      className="absolute inset-0 z-10 pointer-events-none opacity-30"
      style={{
        background: `linear-gradient(to bottom, transparent, ${color}, transparent)`,
        backgroundSize: "100% 200%",
      }}
      initial={{ backgroundPosition: '0% 0%' }}
      animate={{ backgroundPosition: '0% 100%' }}
      transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
    />
  </>
);

/* ============================================
   RESULT PANEL
   ============================================ */
function ResultPanel({
  label,
  accentColor,
  imageSrc,
  isEmpty,
  description,
  isScanning,
}: {
  label: string;
  accentColor: string;
  imageSrc?: string | null;
  isEmpty: boolean;
  description: string;
  isScanning?: boolean;
}) {
  const [enlarged, setEnlarged] = useState(false);

  return (
    <>
      <div className="relative group w-full">
        {/* Glow effect behind active card */}
        <AnimatePresence>
          {isScanning && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.6 }}
              exit={{ opacity: 0 }}
              className="absolute -inset-[3px] rounded-2xl z-0 blur-md"
              style={{ backgroundColor: accentColor }}
              transition={{ duration: 1, repeat: Infinity, repeatType: 'reverse' }}
            />
          )}
        </AnimatePresence>

        <div className={`glass-card rounded-2xl overflow-hidden flex flex-col h-[60vh] min-h-[400px] relative z-10 border transition-all duration-300 bg-white ${isScanning ? 'border-transparent' : 'border-[oklch(0.91_0.015_285)]'}`}>
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[oklch(0.91_0.015_285)] bg-white/80 backdrop-blur-md z-20">
            <span className="font-bold text-sm text-[oklch(0.14_0.02_275)]">{label}</span>
            <div className="flex items-center gap-2">
              <span
                className="text-[10px] font-bold px-2 py-0.5 rounded-full"
                style={{ background: accentColor + "20", color: accentColor }}
              >
                {label.toUpperCase()}
              </span>
              {!isEmpty && imageSrc && (
                <button
                  onClick={() => setEnlarged(true)}
                  className="w-6 h-6 rounded flex items-center justify-center hover:bg-[oklch(0.94_0.05_290)] transition-colors"
                  title="Expand"
                >
                  <Maximize2 className="w-3.5 h-3.5 text-[oklch(0.55_0.04_280)]" />
                </button>
              )}
            </div>
          </div>

          {/* Image Container */}
          <div className="flex-1 bg-[#06060f] relative flex items-center justify-center overflow-hidden">
            {isEmpty ? (
              <div className="flex flex-col items-center gap-4 text-center p-6 z-20">
                {isScanning ? (
                  <>
                    <div className="w-12 h-12 rounded-full border-4 border-t-transparent animate-spin" style={{ borderColor: accentColor, borderTopColor: 'transparent' }} />
                    <p className="text-sm font-medium animate-pulse" style={{ color: accentColor }}>Processing {label}...</p>
                  </>
                ) : (
                  <>
                    <ImageIcon className="w-9 h-9 text-[oklch(0.3_0.05_285)]" />
                    <p className="text-xs text-[oklch(0.35_0.05_280)]">{description}</p>
                  </>
                )}
              </div>
            ) : (
              <AnimatePresence>
                {imageSrc && (
                  <motion.img
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.8, ease: "easeOut" }}
                    src={imageSrc}
                    alt={label}
                    className="w-full h-full object-contain z-10"
                  />
                )}
              </AnimatePresence>
            )}

            {/* Scanner Overlay applies only if actively scanning AND not empty */}
            {isScanning && !isEmpty && <ScanningLaser color={accentColor} />}
          </div>

          {/* Footer */}
          <div className="px-4 py-2 text-xs text-[oklch(0.55_0.04_280)] border-t border-[oklch(0.91_0.015_285)] truncate bg-white z-20">
            {description}
          </div>
        </div>
      </div>

      {/* Lightbox */}
      {enlarged && imageSrc && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-6"
          onClick={() => setEnlarged(false)}
        >
          <div className="relative max-w-5xl w-full flex flex-col items-center" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setEnlarged(false)}
              className="absolute -top-12 right-0 w-10 h-10 bg-white/10 hover:bg-white/20 text-white rounded-full flex items-center justify-center backdrop-blur-md transition-colors"
            >
              <X className="w-6 h-6" />
            </button>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={imageSrc} alt={label} className="w-full h-auto max-h-[85vh] rounded-xl object-contain shadow-2xl" />
            <p className="text-center text-white/70 text-sm mt-4">{label} — {description}</p>
          </div>
        </div>
      )}
    </>
  );
}

/* ============================================
   ROUTING BANNER
   ============================================ */
function RoutingBanner({ result }: { result: DenoiseResponse }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`rounded-xl p-4 flex items-start gap-3 border mb-6 shadow-sm ${
        result.was_bypassed
          ? "bg-emerald-50 border-emerald-200"
          : "bg-[oklch(0.96_0.02_290)] border-[oklch(0.88_0.09_290)]"
      }`}
    >
      {result.was_bypassed
        ? <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
        : <Zap className="w-5 h-5 text-[oklch(0.52_0.22_290)] flex-shrink-0 mt-0.5" />
      }
      <div>
        <p className={`font-semibold text-sm ${result.was_bypassed ? "text-emerald-800" : "text-[oklch(0.35_0.12_285)]"}`}>
          {result.routing_message}
        </p>
        <p className="text-xs mt-0.5 text-[oklch(0.55_0.04_280)]">
          Measured flat-tissue noise variance: <strong>{result.noise_variance.toFixed(2)}</strong>
          {" · "}Image: {result.width} × {result.height} px
        </p>
      </div>
    </motion.div>
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
   DENOISE PAGE
   ============================================ */
export default function DenoisePage() {
  const [file, setFile] = useState<File | null>(null);
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  const [stage, setStage] = useState<AnimationStage>("idle");
  const [result, setResult] = useState<DenoiseResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  const checkBackend = useCallback(async () => {
    try {
      await checkHealth();
      setBackendOnline(true);
    } catch {
      setBackendOnline(false);
    }
  }, []);

  useEffect(() => { checkBackend(); }, [checkBackend]);

  const handleFile = (f: File) => {
    setFile(f);
    setLocalPreview(URL.createObjectURL(f));
    setResult(null);
    setErrorMsg("");
    setStage("idle");
  };

  const handleClear = () => {
    setFile(null);
    setLocalPreview(null);
    setResult(null);
    setErrorMsg("");
    setStage("idle");
  };

  const handleProcess = async () => {
    if (!file) return;

    setResult(null);
    setErrorMsg("");
    setStage("scanning_original");

    // Enforce minimum animation time (1.5 seconds per stage)
    const minOriginalWait = new Promise(resolve => setTimeout(resolve, 1500));

    try {
      // 1. Start original scan animation and wait for API + minimum time
      const apiPromise = denoiseImage(file);
      const [data] = await Promise.all([apiPromise, minOriginalWait]);

      // 2. API returned, move to noise map scan animation
      setResult(data);
      setStage("scanning_noise");

      // 3. Ensure noise map gets its 1.5s of animation glory
      await new Promise(resolve => setTimeout(resolve, 1500));

      // 4. Finally show the enhanced output
      setStage("done");
      setBackendOnline(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error occurred";
      setErrorMsg(msg);
      setStage("error");
      setBackendOnline(false);
    }
  };

  const isProcessing = stage === "scanning_original" || stage === "scanning_noise";
  const isDone = stage === "done";
  const isError = stage === "error";

  // Visibility Logic
  const showOriginal = stage !== "idle";
  const showNoise = stage === "scanning_noise" || stage === "done";
  const showEnhanced = stage === "done";

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
          {/* Upload card */}
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
                  onClick={handleProcess}
                >
                  {isDone ? (
                    <><RefreshCw className="w-4 h-4" /> Re-process</>
                  ) : (
                    <><Zap className="w-4 h-4" /> Enhance X-Ray <ArrowRight className="w-4 h-4" /></>
                  )}
                </Button>
              </motion.div>
            )}

            {isProcessing && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-5 flex items-center gap-3 text-sm text-[oklch(0.52_0.22_290)] font-medium">
                <div className="w-4 h-4 rounded-full border-2 border-[oklch(0.52_0.22_290)] border-t-transparent animate-spin" />
                {stage === "scanning_original" ? "Initializing AI Engine & Analyzing Image..." : "Generating Noise Map & Enhancing..."}
              </motion.div>
            )}
          </div>

          {/* Info & Stats */}
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

            {/* Inference stats (only shows when done) */}
            <AnimatePresence>
              {isDone && result && (
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
                      { label: "Routing",       value: result.was_bypassed ? "Bypassed" : "Processed" },
                      { label: "Noise Var.",     value: result.noise_variance.toFixed(2) },
                      { label: "Enhancement",    value: "CLAHE+USM" },
                      { label: "Time",           value: `${result.processing_time_ms.toFixed(0)} ms` },
                    ].map((s) => (
                      <div key={s.label} className="stat-card !py-3 !px-3 flex flex-col items-center justify-center text-center">
                        <div className="font-bold text-gradient text-sm md:text-base leading-tight">{s.value}</div>
                        <div className="text-[10px] md:text-xs text-[oklch(0.55_0.04_280)] mt-1 uppercase tracking-wider">{s.label}</div>
                      </div>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
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
                Make sure the backend is running:{" "}
                <code className="bg-red-100 px-1.5 py-0.5 rounded font-mono text-red-800">
                  uvicorn main:app --reload
                </code>{" "}
                in the <code className="bg-red-100 px-1.5 py-0.5 rounded font-mono text-red-800">backend/</code> directory.
              </p>
            </div>
          </motion.div>
        )}

        {/* ── Routing Banner ── */}
        {isDone && result && <RoutingBanner result={result} />}

        {/* ── Bottom Section: 3 Card View ── */}
        <div className="flex flex-col gap-4">
          <h2 className="text-2xl font-bold text-[oklch(0.14_0.02_275)] flex items-center gap-3">
            <Maximize2 className="w-6 h-6 text-[oklch(0.52_0.22_290)]" />
            Analysis Results
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 lg:gap-8">
            <ResultPanel
              label="Original Image"
              accentColor="#6b7280"
              imageSrc={localPreview}
              isEmpty={!showOriginal}
              description="Raw uploaded scan"
              isScanning={stage === "scanning_original"}
            />
            <ResultPanel
              label="Noise Map"
              accentColor="#ef4444"
              imageSrc={result?.noise_map_b64}
              isEmpty={!showNoise}
              description="Isolated residual noise"
              isScanning={stage === "scanning_noise"}
            />
            <ResultPanel
              label="Enhanced Result"
              accentColor="#8b5cf6"
              imageSrc={result?.enhanced_b64}
              isEmpty={!showEnhanced}
              description="Final clinical output"
              isScanning={false}
            />
          </div>
        </div>

      </div>
    </div>
  );
}
